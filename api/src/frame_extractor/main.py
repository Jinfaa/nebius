"""FastAPI application for video frame extraction and analysis."""

import os
import shutil
from dotenv import load_dotenv

load_dotenv()
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, Query, HTTPException, status, Body, Form
from fastapi.responses import FileResponse, StreamingResponse
from starlette.background import BackgroundTask
from PIL import Image

from .extractor import iter_frames
from .similarity import is_similar_cached
from .archive import build_zip
from .stitcher import group_and_stitch
from .image_analyzer import analyze_images_batch
from .plan_generator import generate_plan_from_analyses, generate_plan_streaming
from .parser import parse_plan_xml, plan_to_dict

_NEBIUS_API_KEY = os.getenv("NEBIUS_API_KEY")

app = FastAPI(
    title="Video Frame Extractor",
    description="Extracts unique video frames based on SSIM similarity",
    version="0.1.0",
)


@app.post("/extract-frames", response_class=FileResponse)
async def extract_frames(
    file: UploadFile = File(...),
    threshold: float = Query(0.95, ge=0.0, le=1.0),
    quality: int = Query(85, ge=1, le=100),
):
    """
    Extract unique video frames and return as ZIP archive.

    Args:
        file: Video file (mp4, avi, mkv, mov, webm, etc.)
        threshold: SSIM threshold for uniqueness (0-1). Lower = more frames extracted.
        quality: JPEG quality (1-100)

    Returns:
        ZIP file containing extracted frames as JPEG images
    """
    tmp_dir = None
    try:
        tmp_dir = Path(tempfile.mkdtemp(prefix="frames_"))
        frame_dir = tmp_dir / "frames"
        frame_dir.mkdir()

        # Save uploaded file
        video_path = tmp_dir / "input.mp4"
        contents = await file.read()
        if not contents:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty",
            )

        video_path.write_bytes(contents)

        # Extract frames
        prev_thumb = None
        saved_count = 0

        try:
            for frame_index, rgb_array in iter_frames(video_path):
                if prev_thumb is None:
                    saved_count += 1
                    _save_frame(frame_dir, saved_count, rgb_array, quality)
                    prev_thumb = rgb_array
                else:
                    similar, prev_thumb = is_similar_cached(
                        prev_thumb, rgb_array, threshold
                    )
                    if not similar:
                        saved_count += 1
                        _save_frame(frame_dir, saved_count, rgb_array, quality)

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to decode video: {str(e)}",
            )

        if saved_count == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No frames extracted from video",
            )

        # Build ZIP archive
        zip_path = tmp_dir / "frames.zip"
        build_zip(frame_dir, zip_path)

        return FileResponse(
            path=zip_path,
            filename="frames.zip",
            media_type="application/zip",
            background=BackgroundTask(_cleanup, tmp_dir),
        )

    except HTTPException:
        if tmp_dir:
            shutil.rmtree(tmp_dir)
        raise
    except Exception as e:
        if tmp_dir:
            shutil.rmtree(tmp_dir)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


def _save_frame(frame_dir: Path, index: int, rgb_array, quality: int) -> None:
    """Save a frame as JPEG with zero-padded filename."""
    img = Image.fromarray(rgb_array)
    frame_path = frame_dir / f"frame_{index:06d}.jpg"
    img.save(frame_path, "JPEG", quality=quality, optimize=False)


def _cleanup(tmp_dir: Path) -> None:
    """Clean up temporary directory."""
    shutil.rmtree(tmp_dir)


@app.post("/stitch-frames", response_class=FileResponse)
async def stitch_endpoint(
    file: UploadFile = File(...),
    threshold: float = Query(0.95, ge=0.0, le=1.0),
    quality: int = Query(85, ge=1, le=100),
    nebius_api_key: str | None = Query(
        None, description="Nebius AI Studio API key for smart content detection"
    ),
):
    """
    Extract all frames from a screencast/scroll video, group by scene
    (same page = high SSIM), and stitch each scene into a single long screenshot.

    Returns a ZIP with page_001.png, page_002.png, etc.
    """
    tmp_dir = None
    try:
        tmp_dir = Path(tempfile.mkdtemp(prefix="stitch_"))

        video_path = tmp_dir / "input.mp4"
        contents = await file.read()
        if not contents:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty",
            )
        video_path.write_bytes(contents)

        all_frames: list = []
        try:
            for _, rgb_array in iter_frames(video_path):
                all_frames.append(rgb_array)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to decode video: {str(e)}",
            )

        if not all_frames:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No frames extracted from video",
            )

        api_key = nebius_api_key or _NEBIUS_API_KEY
        pages = group_and_stitch(all_frames, scene_threshold=threshold, api_key=api_key)

        output_dir = tmp_dir / "pages"
        output_dir.mkdir()
        for i, page in enumerate(pages, 1):
            Image.fromarray(page).save(output_dir / f"page_{i:03d}.png", "PNG")

        zip_path = tmp_dir / "pages.zip"
        build_zip(output_dir, zip_path)

        return FileResponse(
            path=zip_path,
            filename="pages.zip",
            media_type="application/zip",
            background=BackgroundTask(_cleanup, tmp_dir),
        )

    except HTTPException:
        if tmp_dir:
            shutil.rmtree(tmp_dir)
        raise
    except Exception as e:
        if tmp_dir:
            shutil.rmtree(tmp_dir)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@app.post("/analyze-images")
async def analyze_images(
    files: list[UploadFile] = File(...),
    nebius_api_key: str | None = Query(None, description="Nebius AI API key"),
):
    """
    Analyze uploaded images with Nebius Vision.
    Returns per-image analysis JSON.
    """
    api_key = nebius_api_key or _NEBIUS_API_KEY
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Nebius API key not configured",
        )

    tmp_dir = None
    try:
        tmp_dir = Path(tempfile.mkdtemp(prefix="analyze_"))
        image_paths = []

        for upload_file in files:
            contents = await upload_file.read()
            if not contents:
                continue
            path = tmp_dir / upload_file.filename
            path.write_bytes(contents)
            image_paths.append(str(path))

        if not image_paths:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No valid images provided",
            )

        analyses = analyze_images_batch(image_paths, api_key)

        return {
            "success": True,
            "analyses": analyses,
            "count": len(analyses),
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
    finally:
        if tmp_dir:
            shutil.rmtree(tmp_dir)


@app.post("/generate-plan")
async def generate_plan(
    analyses: list[dict] = Body(...),
    user_message: str | None = Body(None),
    nebius_api_key: str | None = Query(None, description="Nebius AI API key"),
):
    """
    Generate plan from image analyses.
    Returns XML plan with checklist.
    """
    api_key = nebius_api_key or _NEBIUS_API_KEY
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Nebius API key not configured",
        )

    try:
        plan_xml = generate_plan_from_analyses(analyses, api_key, user_message)
        parsed = parse_plan_xml(plan_xml)

        return {
            "xml": plan_xml,
            "parsed": plan_to_dict(parsed),
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@app.post("/generate-plan-streaming")
async def generate_plan_streaming_endpoint(
    analyses: list[dict] = Body(...),
    user_message: str | None = Body(None),
    nebius_api_key: str | None = Query(None, description="Nebius AI API key"),
):
    """
    Generate plan with streaming response.
    """
    api_key = nebius_api_key or _NEBIUS_API_KEY
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Nebius API key not configured",
        )

    def generate():
        for chunk in generate_plan_streaming(analyses, api_key, user_message):
            yield chunk

    return StreamingResponse(
        generate(),
        media_type="text/plain",
    )


@app.post("/analyze-and-plan")
async def analyze_and_plan(
    file: UploadFile = File(...),
    user_message: str | None = Form(None),
    nebius_api_key: str | None = Query(None, description="Nebius AI API key"),
):
    """
    Combined endpoint: analyze video/images + generate plan.
    """
    api_key = nebius_api_key or _NEBIUS_API_KEY
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Nebius API key not configured",
        )

    tmp_dir = None
    try:
        tmp_dir = Path(tempfile.mkdtemp(prefix="analyze_plan_"))

        contents = await file.read()
        if not contents:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty",
            )

        if file.content_type.startswith("video/"):
            video_path = tmp_dir / "input.mp4"
            video_path.write_bytes(contents)

            all_frames = []
            for _, rgb_array in iter_frames(video_path):
                all_frames.append(rgb_array)

            if not all_frames:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No frames extracted from video",
                )

            pages = group_and_stitch(all_frames, scene_threshold=0.95, api_key=api_key)

            page_paths = []
            for i, page in enumerate(pages, 1):
                page_path = tmp_dir / f"page_{i:03d}.png"
                Image.fromarray(page).save(page_path, "PNG")
                page_paths.append(str(page_path))
        else:
            image_path = tmp_dir / file.filename
            image_path.write_bytes(contents)
            page_paths = [str(image_path)]

        analyses = analyze_images_batch(page_paths, api_key)
        plan_xml = generate_plan_from_analyses(analyses, api_key, user_message)
        parsed = parse_plan_xml(plan_xml)

        return {
            "success": True,
            "pages": [
                {"id": f"page_{i}", "filename": Path(p).name}
                for i, p in enumerate(page_paths, 1)
            ],
            "analyses": analyses,
            "plan": plan_to_dict(parsed),
            "xml": plan_xml,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
    finally:
        if tmp_dir:
            shutil.rmtree(tmp_dir)


@app.post("/upload-stream")
async def upload_stream(
    file: UploadFile = File(...),
    user_message: str | None = Form(None),
    nebius_api_key: str | None = Query(None, description="Nebius AI API key"),
):
    """
    Upload video and receive streaming updates via SSE.
    Progress: extracting -> analyzing -> generating -> complete
    """
    import json

    api_key = nebius_api_key or _NEBIUS_API_KEY
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Nebius API key not configured",
        )

    def send_event(event_type: str, data: dict) -> str:
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

    async def generate():
        tmp_dir = None
        try:
            tmp_dir = Path(tempfile.mkdtemp(prefix="upload_stream_"))

            # Step 1: Extract and stitch frames
            yield send_event(
                "progress",
                {
                    "stage": "extracting",
                    "message": "Extracting frames from video...",
                    "progress": 10,
                },
            )

            contents = await file.read()
            if not contents:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Uploaded file is empty",
                )

            if file.content_type.startswith("video/"):
                video_path = tmp_dir / "input.mp4"
                video_path.write_bytes(contents)

                all_frames = []
                for _, rgb_array in iter_frames(video_path):
                    all_frames.append(rgb_array)

                if not all_frames:
                    yield send_event(
                        "error", {"message": "No frames extracted from video"}
                    )
                    return

                yield send_event(
                    "progress",
                    {
                        "stage": "stitching",
                        "message": "Stitching frames into pages...",
                        "progress": 25,
                    },
                )

                pages = group_and_stitch(
                    all_frames, scene_threshold=0.95, api_key=api_key
                )

                page_paths = []
                for i, page in enumerate(pages, 1):
                    page_path = tmp_dir / f"page_{i:03d}.png"
                    Image.fromarray(page).save(page_path, "PNG")
                    page_paths.append(str(page_path))

                yield send_event(
                    "progress",
                    {
                        "stage": "frames_ready",
                        "message": f"Extracted {len(pages)} pages",
                        "progress": 40,
                        "pages": [
                            {"id": f"page_{i}", "filename": Path(p).name}
                            for i, p in enumerate(page_paths, 1)
                        ],
                    },
                )
            else:
                # Handle image directly
                image_path = tmp_dir / file.filename
                image_path.write_bytes(contents)
                page_paths = [str(image_path)]
                yield send_event(
                    "progress",
                    {
                        "stage": "frames_ready",
                        "message": "Image ready",
                        "progress": 40,
                        "pages": [{"id": "page_1", "filename": Path(image_path).name}],
                    },
                )

            # Step 2: Analyze images
            yield send_event(
                "progress",
                {
                    "stage": "analyzing",
                    "message": "Analyzing UI elements with AI...",
                    "progress": 50,
                },
            )

            analyses = analyze_images_batch(page_paths, api_key)

            yield send_event(
                "progress",
                {
                    "stage": "analyzed",
                    "message": f"Analyzed {len(analyses)} images",
                    "progress": 70,
                    "analyses": analyses,
                },
            )

            # Step 3: Generate plan
            yield send_event(
                "progress",
                {
                    "stage": "generating",
                    "message": "Generating implementation plan...",
                    "progress": 80,
                },
            )

            plan_xml = ""
            for chunk in generate_plan_streaming(analyses, api_key, user_message):
                plan_xml += chunk
                yield send_event("chunk", {"content": chunk})

            # Parse plan
            parsed = parse_plan_xml(plan_xml)
            plan_dict = plan_to_dict(parsed)

            # Complete
            yield send_event(
                "complete",
                {
                    "message": "Plan generated successfully",
                    "progress": 100,
                    "pages": [
                        {"id": f"page_{i}", "filename": Path(p).name}
                        for i, p in enumerate(page_paths, 1)
                    ],
                    "analyses": analyses,
                    "plan": plan_dict,
                    "xml": plan_xml,
                },
            )

        except HTTPException:
            raise
        except Exception as e:
            yield send_event("error", {"message": str(e)})
        finally:
            if tmp_dir:
                shutil.rmtree(tmp_dir)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}
