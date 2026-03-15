"""ZIP archive assembly from extracted frames."""

import zipfile
from pathlib import Path


def build_zip(frame_dir: Path, output_path: Path) -> None:
    """
    Build a ZIP archive from all JPEG frames in a directory.

    Args:
        frame_dir: Directory containing frame_XXXXXX.jpg files
        output_path: Path to write the ZIP file
    """
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for jpeg_file in sorted(frame_dir.glob("frame_*.jpg")):
            zf.write(jpeg_file, arcname=jpeg_file.name)
