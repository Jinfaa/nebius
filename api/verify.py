#!/usr/bin/env python3
"""Verification script for frame extractor API."""

import io
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from PIL import Image

from src.frame_extractor.main import app
from fastapi.testclient import TestClient

def create_test_video():
    """Create a simple test video with 30 frames."""
    tmp_dir = Path(tempfile.mkdtemp())
    frame_dir = tmp_dir / "frames"
    frame_dir.mkdir()

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

    # Create MP4 video
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

    return str(video_path), tmp_dir


def main():
    print("=" * 60)
    print("Video Frame Extractor API - Verification")
    print("=" * 60)

    # Create test video
    print("\n1. Creating test video...")
    video_path, tmp_dir = create_test_video()
    print(f"   ✓ Test video created: {video_path}")

    # Test API with client
    print("\n2. Testing API with FastAPI TestClient...")
    client = TestClient(app)

    # Health check
    response = client.get("/health")
    assert response.status_code == 200
    print("   ✓ Health check: OK")

    # Extract frames with default threshold
    with open(video_path, "rb") as f:
        response = client.post(
            "/extract-frames",
            files={"file": ("test.mp4", f, "video/mp4")},
        )

    assert response.status_code == 200, f"Failed: {response.text}"
    print("   ✓ Frame extraction: OK (status 200)")

    # Check ZIP contents
    zip_content = io.BytesIO(response.content)
    with zipfile.ZipFile(zip_content) as zf:
        files = sorted(zf.namelist())
        print(f"   ✓ Extracted {len(files)} unique frames")
        print(f"   ✓ Frame names: {', '.join(files[:3])}..." if len(files) > 3 else f"   ✓ Frame names: {', '.join(files)}")

        # Verify JPEG format
        for fname in files[:1]:
            data = zf.read(fname)
            img = Image.open(io.BytesIO(data))
            assert img.format == "JPEG"
            print(f"   ✓ Frame format: JPEG ({img.size[0]}x{img.size[1]})")

    # Test with custom parameters
    print("\n3. Testing API with custom parameters...")
    with open(video_path, "rb") as f:
        response = client.post(
            "/extract-frames",
            files={"file": ("test.mp4", f, "video/mp4")},
            params={"threshold": 0.5, "quality": 95},
        )

    assert response.status_code == 200
    print("   ✓ Custom parameters: OK")

    # Test validation
    print("\n4. Testing parameter validation...")
    with open(video_path, "rb") as f:
        response = client.post(
            "/extract-frames",
            files={"file": ("test.mp4", f, "video/mp4")},
            params={"threshold": 1.5},  # Invalid
        )

    assert response.status_code == 422
    print("   ✓ Threshold validation: OK (rejected 1.5)")

    with open(video_path, "rb") as f:
        response = client.post(
            "/extract-frames",
            files={"file": ("test.mp4", f, "video/mp4")},
            params={"quality": 101},  # Invalid
        )

    assert response.status_code == 422
    print("   ✓ Quality validation: OK (rejected 101)")

    # Cleanup
    shutil.rmtree(tmp_dir)

    print("\n" + "=" * 60)
    print("✓ All verification tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
