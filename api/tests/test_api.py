"""Tests for frame extraction API."""

import io
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from frame_extractor.main import app


@pytest.fixture
def test_video():
    """Create a test video with 30 frames (10 red, 10 blue, 10 green) using PIL frames."""

    tmp_dir = Path(tempfile.mkdtemp())
    frame_dir = tmp_dir / "frames"
    frame_dir.mkdir()

    # Create 30 solid color frames as PNG
    width, height = 640, 480
    frame_count = 0

    # 10 red frames
    red_img = Image.new("RGB", (width, height), (255, 0, 0))
    for i in range(10):
        frame_count += 1
        red_img.save(frame_dir / f"frame_{frame_count:05d}.png")

    # 10 blue frames
    blue_img = Image.new("RGB", (width, height), (0, 0, 255))
    for i in range(10):
        frame_count += 1
        blue_img.save(frame_dir / f"frame_{frame_count:05d}.png")

    # 10 green frames
    green_img = Image.new("RGB", (width, height), (0, 255, 0))
    for i in range(10):
        frame_count += 1
        green_img.save(frame_dir / f"frame_{frame_count:05d}.png")

    # Create MP4 video from frames using ffmpeg
    video_path = tmp_dir / "test.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-framerate",
            "10",
            "-i",
            str(frame_dir / "frame_%05d.png"),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(video_path),
        ],
        check=True,
        capture_output=True,
    )

    yield str(video_path)

    shutil.rmtree(tmp_dir)


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


def test_extract_frames_default_threshold(client, test_video):
    """Test frame extraction with default threshold (should extract 3 unique frames)."""
    with open(test_video, "rb") as f:
        response = client.post(
            "/extract-frames",
            files={"file": ("test.mp4", f, "video/mp4")},
        )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"

    # Parse ZIP
    zip_content = io.BytesIO(response.content)
    with zipfile.ZipFile(zip_content) as zf:
        names = zf.namelist()
        assert len(names) == 3, f"Expected 3 frames, got {len(names)}: {names}"
        assert all(n.startswith("frame_") and n.endswith(".jpg") for n in names)


def test_extract_frames_threshold_variation(client, test_video):
    """Test that threshold affects number of extracted frames."""
    # With threshold=0.95 (default): Should extract keyframes when color changes significantly
    with open(test_video, "rb") as f:
        response_default = client.post(
            "/extract-frames",
            files={"file": ("test.mp4", f, "video/mp4")},
            params={"threshold": 0.95},
        )

    # With threshold=0.5: More conservative, extracts fewer frames
    with open(test_video, "rb") as f:
        response_strict = client.post(
            "/extract-frames",
            files={"file": ("test.mp4", f, "video/mp4")},
            params={"threshold": 0.5},
        )

    assert response_default.status_code == 200
    assert response_strict.status_code == 200

    default_frames = len(zipfile.ZipFile(io.BytesIO(response_default.content)).namelist())
    strict_frames = len(zipfile.ZipFile(io.BytesIO(response_strict.content)).namelist())

    # Stricter threshold (0.5) should extract fewer or equal frames
    assert strict_frames <= default_frames


def test_extract_frames_custom_quality(client, test_video):
    """Test with custom JPEG quality."""
    with open(test_video, "rb") as f:
        response = client.post(
            "/extract-frames",
            files={"file": ("test.mp4", f, "video/mp4")},
            params={"quality": 50},
        )

    assert response.status_code == 200

    zip_content = io.BytesIO(response.content)
    with zipfile.ZipFile(zip_content) as zf:
        assert len(zf.namelist()) > 0


def test_extract_frames_invalid_threshold_too_high(client, test_video):
    """Test validation: threshold > 1.0 should fail."""
    with open(test_video, "rb") as f:
        response = client.post(
            "/extract-frames",
            files={"file": ("test.mp4", f, "video/mp4")},
            params={"threshold": 1.5},
        )

    assert response.status_code == 422


def test_extract_frames_invalid_threshold_negative(client, test_video):
    """Test validation: threshold < 0.0 should fail."""
    with open(test_video, "rb") as f:
        response = client.post(
            "/extract-frames",
            files={"file": ("test.mp4", f, "video/mp4")},
            params={"threshold": -0.1},
        )

    assert response.status_code == 422


def test_extract_frames_invalid_quality_too_high(client, test_video):
    """Test validation: quality > 100 should fail."""
    with open(test_video, "rb") as f:
        response = client.post(
            "/extract-frames",
            files={"file": ("test.mp4", f, "video/mp4")},
            params={"quality": 101},
        )

    assert response.status_code == 422


def test_extract_frames_invalid_quality_zero(client, test_video):
    """Test validation: quality < 1 should fail."""
    with open(test_video, "rb") as f:
        response = client.post(
            "/extract-frames",
            files={"file": ("test.mp4", f, "video/mp4")},
            params={"quality": 0},
        )

    assert response.status_code == 422


def test_extract_frames_empty_file(client):
    """Test with empty file."""
    response = client.post(
        "/extract-frames",
        files={"file": ("empty.mp4", io.BytesIO(b""), "video/mp4")},
    )

    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


def test_extract_frames_invalid_file(client):
    """Test with non-video file."""
    response = client.post(
        "/extract-frames",
        files={"file": ("invalid.mp4", io.BytesIO(b"not a video"), "video/mp4")},
    )

    assert response.status_code == 400


def test_health_endpoint(client):
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_frame_filenames_sequential(client, test_video):
    """Test that frames are numbered sequentially with zero-padding."""
    with open(test_video, "rb") as f:
        response = client.post(
            "/extract-frames",
            files={"file": ("test.mp4", f, "video/mp4")},
            params={"threshold": 0.0},
        )

    assert response.status_code == 200

    zip_content = io.BytesIO(response.content)
    with zipfile.ZipFile(zip_content) as zf:
        names = sorted(zf.namelist())
        for i, name in enumerate(names, start=1):
            assert name == f"frame_{i:06d}.jpg", f"Expected frame_{i:06d}.jpg, got {name}"


def test_frames_are_valid_jpegs(client, test_video):
    """Test that extracted frames are valid JPEG images."""
    with open(test_video, "rb") as f:
        response = client.post(
            "/extract-frames",
            files={"file": ("test.mp4", f, "video/mp4")},
        )

    assert response.status_code == 200

    zip_content = io.BytesIO(response.content)
    with zipfile.ZipFile(zip_content) as zf:
        for name in zf.namelist():
            frame_data = zf.read(name)
            img = Image.open(io.BytesIO(frame_data))
            assert img.format == "JPEG"
            assert img.size == (640, 480)
