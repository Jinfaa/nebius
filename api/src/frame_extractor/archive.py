"""ZIP archive assembly from extracted frames."""

import zipfile
from pathlib import Path


def build_zip(frame_dir: Path, output_path: Path) -> None:
    """
    Build a ZIP archive from all image files in a directory.

    Args:
        frame_dir: Directory containing image files
        output_path: Path to write the ZIP file
    """
    files = sorted(frame_dir.glob("frame_*.jpg")) or sorted(frame_dir.glob("page_*.png"))
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f, arcname=f.name)
