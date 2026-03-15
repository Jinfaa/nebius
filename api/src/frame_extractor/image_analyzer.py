"""
Image Analysis Module.
Analyze screenshots with Nebius Vision model.
"""

import base64
import io
import json
from pathlib import Path
from PIL import Image

from .providers import get_provider
from .prompts import IMAGE_ANALYSIS_PROMPT


def encode_image_to_base64(image_path: str, max_dim: int = 1024) -> str:
    """
    Encode image to base64 for API calls.

    Args:
        image_path: Path to the image file
        max_dim: Maximum dimension for resizing

    Returns:
        Base64-encoded image string
    """
    img = Image.open(image_path)

    # Convert RGBA to RGB if needed
    if img.mode == "RGBA":
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[3])
        img = background

    scale = max_dim / max(img.size)
    if scale < 1.0:
        img = img.resize(
            (int(img.width * scale), int(img.height * scale)),
            Image.Resampling.BILINEAR,
        )

    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


def analyze_single_image(
    image_path: str,
    api_key: str,
    image_id: str | None = None,
) -> dict:
    """
    Analyze a single image with Nebius Vision.

    Args:
        image_path: Path to the image file
        api_key: Nebius API key
        image_id: Optional identifier for the image

    Returns:
        Dictionary with analysis results
    """
    b64 = encode_image_to_base64(image_path)
    provider = get_provider(api_key)

    result = provider.vision_chat_json(
        image_base64=b64,
        prompt=IMAGE_ANALYSIS_PROMPT,
    )

    # Add image_id if provided
    if image_id:
        result["image_id"] = image_id

    return result


def analyze_single_image_from_bytes(
    image_bytes: bytes,
    api_key: str,
    image_id: str | None = None,
) -> dict:
    """
    Analyze a single image from bytes with Nebius Vision.

    Args:
        image_bytes: Raw image bytes
        api_key: Nebius API key
        image_id: Optional identifier for the image

    Returns:
        Dictionary with analysis results
    """
    # Encode bytes to base64
    b64 = base64.b64encode(image_bytes).decode()
    provider = get_provider(api_key)

    result = provider.vision_chat_json(
        image_base64=b64,
        prompt=IMAGE_ANALYSIS_PROMPT,
    )

    # Add image_id if provided
    if image_id:
        result["image_id"] = image_id

    return result


def analyze_images_batch(
    image_paths: list[str],
    api_key: str,
) -> list[dict]:
    """
    Analyze multiple images sequentially.

    Args:
        image_paths: List of paths to image files
        api_key: Nebius API key

    Returns:
        List of analysis dictionaries
    """
    analyses = []
    for i, path in enumerate(image_paths, 1):
        analysis = analyze_single_image(
            path,
            api_key,
            image_id=f"page_{i}",
        )
        analyses.append(analysis)

    return analyses


def analyze_images_from_directory(
    directory: str,
    api_key: str,
    pattern: str = "*.png",
) -> list[dict]:
    """
    Analyze all images in a directory.

    Args:
        directory: Path to directory containing images
        api_key: Nebius API key
        pattern: Glob pattern for image files

    Returns:
        List of analysis dictionaries
    """
    dir_path = Path(directory)
    image_paths = sorted(dir_path.glob(pattern))

    if not image_paths:
        # Try with .jpg extension
        image_paths = sorted(dir_path.glob("*.jpg"))

    if not image_paths:
        # Try with .jpeg extension
        image_paths = sorted(dir_path.glob("*.jpeg"))

    if not image_paths:
        raise ValueError(f"No images found in {directory} with pattern {pattern}")

    return analyze_images_batch([str(p) for p in image_paths], api_key)
