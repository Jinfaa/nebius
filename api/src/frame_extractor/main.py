"""FastAPI application for video frame extraction and analysis."""

import logging
import os
import shutil
from dotenv import load_dotenv

load_dotenv()
import tempfile
from pathlib import Path
import numpy as np
from PIL import Image

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from fastapi import (
    FastAPI,
    File,
    UploadFile,
    Query,
    HTTPException,
    status,
    Body,
    Form,
    Request,
)
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
from .providers import get_provider

_NEBIUS_API_KEY = os.getenv("NEBIUS_API_KEY")
_IFRAME_DIR = "/tmp/site"

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Video Frame Extractor",
    description="Extracts unique video frames based on SSIM similarity",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
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
        import sys

        result = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
        sys.stdout.flush()
        return result

    import logging

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    logger.info("=== upload-stream endpoint called ===")

    def ensure_iframe_dev_server():
        """Ensure /tmp/site has a Next.js project and dev server running."""
        import subprocess

        iframe_dir = Path(_IFRAME_DIR)
        if not iframe_dir.exists() or not (iframe_dir / "package.json").exists():
            iframe_dir.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                [
                    "pnpm",
                    "create",
                    "next-app",
                    ".",
                    "--typescript",
                    "--tailwind",
                    "--app",
                    "--src-dir",
                    "--import-alias",
                    "@/*",
                    "--use-pnpm",
                    "--yes",
                ],
                cwd=iframe_dir,
                check=True,
            )

        pid_file = iframe_dir / ".dev-server.pid"
        if pid_file.exists():
            try:
                pid = int(pid_file.read_text().strip())
                import os

                os.kill(pid, 0)
                return
            except:
                pid_file.unlink()

        import subprocess

        proc = subprocess.Popen(
            ["pnpm", "run", "dev", "--port", "3040"],
            cwd=iframe_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if proc.pid:
            pid_file.write_text(str(proc.pid))

    async def generate():
        tmp_dir = None
        try:
            tmp_dir = Path(tempfile.mkdtemp(prefix="upload_stream_"))

            logger.info("Starting upload-stream process")
            logger.info("Step 1: Reading uploaded file")

            contents = await file.read()
            logger.info(f"File size: {len(contents)} bytes, type: {file.content_type}")
            if not contents:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Uploaded file is empty",
                )

            if file.content_type.startswith("video/"):
                video_path = tmp_dir / "input.mp4"
                video_path.write_bytes(contents)
                logger.info("Step 2: Extracting frames from video")

                all_frames = []
                frame_idx = 0
                for _, rgb_array in iter_frames(video_path):
                    all_frames.append(rgb_array)
                    frame_idx += 1
                    if frame_idx % 30 == 0:
                        logger.info(f"Extracted {frame_idx} frames...")

                logger.info(f"Total frames extracted: {len(all_frames)}")

                if not all_frames:
                    yield send_event(
                        "error", {"message": "No frames extracted from video"}
                    )
                    return

                yield send_event(
                    "progress",
                    {
                        "stage": "stitching",
                        "message": "🔗 Processing video frames...",
                        "progress": 25,
                    },
                )
                logger.info("Step 3: Grouping and stitching frames")

                pages = group_and_stitch(
                    all_frames, scene_threshold=0.95, api_key=api_key
                )
                logger.info(f"Stitched into {len(pages)} pages")

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
                    "message": "🤖 Analyzing UI with AI (this may take a minute)...",
                    "progress": 50,
                },
            )
            logger.info(f"Step 4: Analyzing {len(page_paths)} images with AI...")

            analyses = analyze_images_batch(page_paths, api_key)
            logger.info(f"Analyzed {len(analyses)} images")

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
                    "message": "📋 Generating implementation plan...",
                    "progress": 80,
                },
            )
            logger.info("Step 5: Generating implementation plan with LLM...")

            plan_xml = ""
            for chunk in generate_plan_streaming(analyses, api_key, user_message):
                plan_xml += chunk
                yield send_event("chunk", {"content": chunk})

            # Parse plan
            parsed = parse_plan_xml(plan_xml)
            plan_dict = plan_to_dict(parsed)

            # Start iframe dev server in background (don't wait)
            import threading

            logger.info("Step 6: Starting iframe dev server in background...")
            threading.Thread(target=ensure_iframe_dev_server, daemon=True).start()

            # Complete
            logger.info("Upload-stream complete! Sending to frontend")
            yield send_event(
                "complete",
                {
                    "message": "✅ Done! Opening chat...",
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
            logger.error(f"Error in upload-stream: {e}")
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


@app.post("/upload-start")
async def upload_start(
    file: UploadFile = File(...),
    nebius_api_key: str | None = Query(None, description="Nebius AI API key"),
):
    """
    Start upload - saves file to temp dir, returns uploadId immediately.
    Client then connects to /upload-progress/{uploadId} for streaming updates.
    """
    import uuid

    api_key = nebius_api_key or _NEBIUS_API_KEY
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Nebius API key not configured",
        )

    upload_id = str(uuid.uuid4())
    upload_dir = Path(_IFRAME_DIR).parent / "uploads" / upload_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    contents = await file.read()
    if not contents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty",
        )

    file_path = upload_dir / file.filename
    file_path.write_bytes(contents)

    return {
        "uploadId": upload_id,
        "filename": file.filename,
        "message": "File uploaded. Connect to /upload-progress for processing.",
    }


@app.get("/upload-progress/{upload_id}")
async def upload_progress(upload_id: str):
    """
    SSE endpoint for processing uploaded file.
    Shows all steps in real-time: extracting -> stitching -> analyzing -> generating -> complete
    """
    import json

    api_key = _NEBIUS_API_KEY
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Nebius API key not configured",
        )

    def send_event(event_type: str, data: dict) -> str:
        import sys

        result = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
        sys.stdout.flush()
        return result

    upload_dir = Path(_IFRAME_DIR).parent / "uploads" / upload_id

    if not upload_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload not found",
        )

    files = list(upload_dir.iterdir())
    if not files:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No files found for upload",
        )

    file_path = files[0]
    file = file_path
    file_content_type = (
        "video/mp4"
        if file.suffix.lower() in [".mp4", ".mov", ".avi", ".mkv", ".webm"]
        else "image/png"
    )

    async def generate():
        import asyncio
        from .image_analyzer import analyze_single_image

        try:
            logger.info(f"Starting upload-progress for {upload_id}")

            if file_content_type.startswith("video/"):
                yield send_event(
                    "progress",
                    {
                        "stage": "extracting",
                        "message": "📹 Extracting frames from video...",
                        "progress": 5,
                    },
                )
                await asyncio.sleep(0)

                all_frames = []
                frame_idx = 0
                for _, rgb_array in iter_frames(file):
                    all_frames.append(rgb_array)
                    frame_idx += 1
                    if frame_idx % 30 == 0:
                        yield send_event(
                            "progress",
                            {
                                "stage": "extracting",
                                "message": f"📹 Extracting frames: {frame_idx} processed...",
                                "progress": 5,
                            },
                        )
                        await asyncio.sleep(0)

                if not all_frames:
                    yield send_event("error", {"message": "No frames extracted"})
                    return

                yield send_event(
                    "progress",
                    {
                        "stage": "extracting",
                        "message": f"📹 Extracted {len(all_frames)} frames total",
                        "progress": 15,
                    },
                )
                await asyncio.sleep(0)

                yield send_event(
                    "progress",
                    {
                        "stage": "stitching",
                        "message": "🔗 Grouping frames by screen and stitching pages...",
                        "progress": 20,
                    },
                )
                await asyncio.sleep(0)

                pages = group_and_stitch(
                    all_frames, scene_threshold=0.95, api_key=api_key
                )

                yield send_event(
                    "progress",
                    {
                        "stage": "stitching",
                        "message": f"🔗 Assembled {len(pages)} unique screen(s)",
                        "progress": 35,
                    },
                )
                await asyncio.sleep(0)
            else:
                yield send_event(
                    "progress",
                    {
                        "stage": "extracting",
                        "message": "📷 Processing image...",
                        "progress": 10,
                    },
                )
                await asyncio.sleep(0)

                img = Image.open(file)
                pages = [np.array(img)]

                yield send_event(
                    "progress",
                    {
                        "stage": "stitching",
                        "message": "🔗 Image ready",
                        "progress": 35,
                    },
                )
                await asyncio.sleep(0)

            page_paths = []
            for i, page in enumerate(pages, 1):
                page_path = upload_dir / f"page_{i:03d}.png"
                Image.fromarray(page).save(page_path, "PNG")
                page_paths.append(str(page_path))

            total_pages = len(page_paths)
            analyses = []
            for i, path in enumerate(page_paths, 1):
                yield send_event(
                    "progress",
                    {
                        "stage": "analyzing",
                        "message": f"🤖 Analyzing screen {i} of {total_pages} with AI...",
                        "progress": 35 + int((i - 1) / total_pages * 35),
                    },
                )
                await asyncio.sleep(0)

                analysis = analyze_single_image(path, api_key, image_id=f"page_{i}")
                analyses.append(analysis)

                yield send_event(
                    "progress",
                    {
                        "stage": "analyzing",
                        "message": f"✅ Screen {i} of {total_pages} analyzed",
                        "progress": 35 + int(i / total_pages * 35),
                    },
                )
                await asyncio.sleep(0)

            yield send_event(
                "progress",
                {
                    "stage": "generating",
                    "message": "📋 Generating implementation plan...",
                    "progress": 75,
                },
            )
            await asyncio.sleep(0)

            plan_xml = ""
            for chunk in generate_plan_streaming(analyses, api_key, None):
                plan_xml += chunk
                yield send_event("chunk", {"content": chunk})
                await asyncio.sleep(0)

            yield send_event(
                "progress",
                {
                    "stage": "generating",
                    "message": "📋 Plan generated, preparing chat...",
                    "progress": 95,
                },
            )
            await asyncio.sleep(0)

            parsed = parse_plan_xml(plan_xml)
            plan_dict = plan_to_dict(parsed)
            await asyncio.sleep(0)

            yield send_event(
                "complete",
                {
                    "message": "✅ Done! Opening chat...",
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

            logger.info(f"Upload-progress complete for {upload_id}")

        except Exception as e:
            logger.error(f"Error in upload-progress: {e}")
            yield send_event("error", {"message": str(e)})

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


@app.post("/generate-code-streaming")
async def generate_code_streaming(request: Request):
    """
    Generate code from plan using LLM, stream SSE with actions.
    Receives: { messages, plan, xml }
    Returns: SSE with thinking, description, action, complete events
    """
    import json
    import re
    from .providers import NebiusProvider

    api_key = _NEBIUS_API_KEY
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Nebius API key not configured",
        )

    def send_event(event_type: str, data: dict) -> str:
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

    async def generate():
        try:
            body = await request.json()
            messages = body.get("messages", [])
            plan = body.get("plan", {})
            xml = body.get("xml", "")

            plan_description = plan.get("planDescription", "")
            checklist = plan.get("checklist", [])

            context_parts = [
                f"# Implementation Plan\n\n{plan_description}\n\n",
                "## Checklist\n",
            ]
            for item in checklist:
                status_icon = "x" if item.get("status") == "done" else " "
                context_parts.append(
                    f"- [{status_icon}] [{item.get('category', '')}] {item.get('description', '')}\n"
                )

            if xml:
                context_parts.append(f"\n## XML Plan\n\n{xml}\n")

            context = "".join(context_parts)

            system_prompt = """# AI Assistant System Prompt

You are Libra, an AI editor for creating and modifying web applications. You help users through chat while making real-time code modifications. Users can view application previews in the left-side iframe while you implement code changes.

## Tech Stack
- React 19 and TypeScript 5.8
- Vite 6.2 build tool
- shadcn/ui components (based on Radix UI)
- Tailwind CSS 3.4
- lucide-react for icons

## Project Structure
- src/
    - components/: reusable React components
    - hooks/: custom React hooks
    - lib/: utilities and configurations
    - pages/: page components
    - App.tsx: main application
    - main.tsx: entry point
    - index.css: global styles

## Response Format (Absolutely Mandatory)

Your response **must strictly follow** this XML structure:

1. **<thinking>** (mandatory): Your detailed reasoning in <![CDATA[...]]>
2. **<planDescription>** (mandatory): Clear overview in <![CDATA[...]]>
3. **<action>** elements (required when changes occur):
   - For file changes: type="file"
     - <file filename="path/to/file.tsx"> with code in <![CDATA[...]]>
     - <description> describing the change
   - For commands: type="command"
     - <commandType> e.g., "bun install"
     - <package> package name

## Important
- Write complete, working code - never truncate code in <![CDATA[...]]>
- Use Tailwind CSS for styling
- Use shadcn/ui components when appropriate
- Keep components small and focused

## User Request
"""

            user_message = (
                context
                + "\n\n---\n\n"
                + "Generate code for the implementation plan above. Create all necessary files in the src/ directory."
            )

            llm_messages = [{"role": "user", "content": user_message}]

            provider = NebiusProvider(api_key)

            yield send_event("thinking", {"content": "", "type": "start"})

            full_response = ""
            thinking_buffer = ""
            description_buffer = ""
            action_buffer = ""
            current_section = None

            for chunk in provider.chat(llm_messages, system_prompt=system_prompt):
                full_response += chunk

                thinking_buffer += chunk
                if "<planDescription>" in thinking_buffer:
                    if current_section is None or current_section == "thinking":
                        thinking_part = thinking_buffer.split("<planDescription>")[0]
                        if "<![CDATA[" in thinking_part:
                            think_content = thinking_part.split("<![CDATA[")[1]
                            if "]]>" in think_content:
                                think_text = think_content.split("]]>")[0]
                                yield send_event("thinking", {"content": think_text})
                                current_section = "thinking"

                if "<action>" in full_response:
                    if current_section != "action_started":
                        yield send_event(
                            "description_complete",
                            {"content": description_buffer.strip()},
                        )
                        current_section = "action_started"

                for match in re.finditer(
                    r'<action\s+type="file">\s*<file\s+filename="([^"]+)">\s*<!\CDATA\[([^\]]+)\]\]>\s*</file>\s*<description><!\CDATA\[([^\]]+)\]\]></description>\s*</action>',
                    full_response,
                    re.DOTALL,
                ):
                    filename = match.group(1)
                    content = match.group(2)
                    description = match.group(3)

                    file_path = Path(_IFRAME_DIR) / filename
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    file_path.write_text(content)

                    yield send_event(
                        "action",
                        {
                            "type": "file",
                            "path": filename,
                            "description": description,
                        },
                    )

                for match in re.finditer(
                    r'<action\s+type="command">\s*<commandType>([^<]+)</commandType>\s*<package>([^<]*)</package>\s*</action>',
                    full_response,
                ):
                    cmd_type = match.group(1).strip()
                    package = match.group(2).strip()

                    yield send_event(
                        "action",
                        {
                            "type": "command",
                            "commandType": cmd_type,
                            "package": package,
                        },
                    )

            yield send_event("thinking_complete", {"content": ""})
            yield send_event(
                "description_complete",
                {"content": description_buffer.strip() if description_buffer else ""},
            )
            yield send_event("complete", {"message": "Code generation complete"})

        except HTTPException:
            raise
        except Exception as e:
            yield send_event("error", {"message": str(e)})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
