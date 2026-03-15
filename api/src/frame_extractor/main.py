"""FastAPI application for video frame extraction."""

import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, Query, HTTPException, status
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from PIL import Image

from .extractor import iter_frames
from .similarity import is_similar_cached
from .archive import build_zip
from .stitcher import group_and_stitch

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
    nebius_api_key: str | None = Query(None, description="Nebius AI Studio API key for smart content detection"),
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

        pages = group_and_stitch(all_frames, scene_threshold=threshold, api_key=nebius_api_key)

        output_dir = tmp_dir / "pages"
        output_dir.mkdir()
        for i, page in enumerate(pages, 1):
            Image.fromarray(page).save(
                output_dir / f"page_{i:03d}.png", "PNG"
            )

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


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}
