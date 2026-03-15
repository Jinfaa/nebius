"""SSIM-based frame similarity comparison."""

import numpy as np
from PIL import Image
from skimage.metrics import structural_similarity

_MAX_DIM = 256


def _to_gray_thumbnail(frame: np.ndarray) -> np.ndarray:
    """Convert RGB frame to grayscale thumbnail (max 256px) as numpy array."""
    img = Image.fromarray(frame)
    scale = _MAX_DIM / max(img.size)
    if scale < 1.0:
        new_size = (int(img.size[0] * scale), int(img.size[1] * scale))
        img = img.resize(new_size, Image.Resampling.BILINEAR)
    return np.array(img.convert("L"))


def is_similar(frame_a: np.ndarray, frame_b: np.ndarray, threshold: float) -> bool:
    """
    Check if two frames are similar using SSIM.

    Downscales to 256px, converts to grayscale, computes SSIM.
    Returns True if SSIM > threshold (frames are similar, should be skipped).
    """
    gray_a = _to_gray_thumbnail(frame_a)
    gray_b = _to_gray_thumbnail(frame_b)

    if gray_a.shape != gray_b.shape:
        return False

    score = structural_similarity(gray_a, gray_b)
    return score > threshold


def is_similar_cached(
    prev_thumb: np.ndarray,
    frame_b: np.ndarray,
    threshold: float,
) -> tuple[bool, np.ndarray]:
    """
    SSIM comparison that caches thumbnails between calls.

    prev_thumb: grayscale thumbnail from previous saved frame (or raw RGB on first call).
    Returns (is_similar, new_thumb_to_cache).
    If similar, returns prev_thumb unchanged. If different, returns current thumbnail.
    """
    if prev_thumb.ndim == 3:
        prev_thumb = _to_gray_thumbnail(prev_thumb)

    cur_thumb = _to_gray_thumbnail(frame_b)

    if prev_thumb.shape != cur_thumb.shape:
        return False, cur_thumb

    score = structural_similarity(prev_thumb, cur_thumb)
    if score > threshold:
        return True, prev_thumb
    return False, cur_thumb
