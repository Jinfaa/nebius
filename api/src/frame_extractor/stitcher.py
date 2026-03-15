"""Vertical stitching of overlapping frames into a single long image."""

import numpy as np
from PIL import Image

_MATCH_SCALE = 0.5
_FRAME_STEP = 3
_SCENE_CHANGE_STREAK = 3
_MEDIAN_WINDOW = 5
_OVERLAY_SAMPLE_COUNT = 8  # frames to sample for overlay detection
_OVERLAY_PRESENCE_RATIO = 0.8  # region must be in >=80% of ALL frames to be "permanent"
_OVERLAY_VAR_THRESHOLD = 15.0  # pixel std below this = "static" region


def _median_frame(frames: list[np.ndarray], center: int) -> np.ndarray:
    """
    Pixel-wise median over STATIC neighbors only (SSIM > 0.999).
    Removes cursor/tooltips while keeping scrolling content sharp.
    """
    from .similarity import _to_gray_thumbnail
    from skimage.metrics import structural_similarity

    half = _MEDIAN_WINDOW // 2
    start = max(0, center - half)
    end = min(len(frames), center + half + 1)

    center_thumb = _to_gray_thumbnail(frames[center])
    static = [frames[center]]

    for j in range(start, end):
        if j == center:
            continue
        other_thumb = _to_gray_thumbnail(frames[j])
        if center_thumb.shape == other_thumb.shape:
            s = structural_similarity(center_thumb, other_thumb)
            if s > 0.999:
                static.append(frames[j])

    if len(static) <= 1:
        return frames[center]

    return np.median(np.stack(static), axis=0).astype(np.uint8)


def _top_band_similar(frame_a: np.ndarray, frame_b: np.ndarray) -> bool:
    """
    Compare the top ~8% of two frames (skipping top 1%).
    This captures browser chrome / app toolbar while skipping OS-level bars.
    Same top band = same page/app context.
    """
    from skimage.metrics import structural_similarity

    h = min(frame_a.shape[0], frame_b.shape[0])
    top = int(h * 0.01)
    bot = int(h * 0.08)

    band_a = np.array(Image.fromarray(frame_a[top:bot]).convert("L"))
    band_b = np.array(Image.fromarray(frame_b[top:bot]).convert("L"))

    if band_a.shape != band_b.shape:
        return False

    return structural_similarity(band_a, band_b) > 0.95


def _downscale_gray(frame: np.ndarray) -> np.ndarray:
    """Downscale an RGB frame to grayscale at _MATCH_SCALE."""
    img = Image.fromarray(frame)
    new_size = (int(img.width * _MATCH_SCALE), int(img.height * _MATCH_SCALE))
    return np.array(img.resize(new_size, Image.Resampling.BILINEAR).convert("L"))


def _find_vertical_offset(prev_gray: np.ndarray, curr_gray: np.ndarray) -> int | None:
    """
    Find vertical scroll offset between two downscaled grayscale frames.

    Returns number of NEW rows (in downscaled coords) at the bottom of curr.
    None = no overlap (scene change). 0 = static (no scroll).
    """
    h, w = prev_gray.shape

    strip_l = int(w * 0.3)
    strip_r = int(w * 0.7)

    template_h = max(min(h // 4, 40), 10)
    template = prev_gray[h - template_h:h, strip_l:strip_r].astype(np.float32)
    t_std = template.std()
    if t_std < 1.0:
        return None

    template_norm = template - template.mean()

    best_score = -1.0
    best_y = 0

    max_shift = h - template_h
    for y in range(0, max_shift + 1):
        region = curr_gray[y:y + template_h, strip_l:strip_r].astype(np.float32)
        r_std = region.std()
        if r_std < 1.0:
            continue
        region_norm = region - region.mean()
        ncc = (template_norm * region_norm).sum() / (t_std * r_std * template_norm.size)
        if ncc > best_score:
            best_score = ncc
            best_y = y

    if best_score < 0.85:
        return None

    new_rows = h - (best_y + template_h)
    return max(new_rows, 0)


def group_and_stitch(
    frames: list[np.ndarray],
    scene_threshold: float = 0.95,
    api_key: str | None = None,
) -> list[np.ndarray]:
    """
    1. Optionally detect content bbox via LLM (first frame) and crop all frames
    2. Template matching to find scroll offsets and scene changes
    3. Stitch each scene into a tall image

    Args:
        frames: list of RGB frames from video
        scene_threshold: SSIM threshold for scene detection
        api_key: Nebius AI Studio API key. If provided, uses LLM vision
                 to detect and crop to website content area (removes OS UI).

    Returns list of stitched images (one per page/scene).
    """
    if not frames:
        return []

    n = len(frames)
    scale_inv = 1.0 / _MATCH_SCALE

    pages: list[np.ndarray] = []
    strips: list[np.ndarray] = [_median_frame(frames, 0)]
    strips_start_idx = 0
    prev_gray = _downscale_gray(frames[0])
    prev_idx = 0

    step = _FRAME_STEP
    i = step
    no_match_streak = 0

    while i < n:
        curr_gray = _downscale_gray(frames[i])
        offset = _find_vertical_offset(prev_gray, curr_gray)

        if offset is None:
            no_match_streak += 1
            if no_match_streak >= _SCENE_CHANGE_STREAK:
                if not _top_band_similar(frames[strips_start_idx], frames[i]):
                    pages.append(np.vstack(strips))
                    strips = [_median_frame(frames, i)]
                    strips_start_idx = i
                no_match_streak = 0
            prev_gray = curr_gray
            prev_idx = i
            step = _FRAME_STEP
        elif offset > 0:
            new_rows_full = int(offset * scale_inv)
            if new_rows_full > 0:
                cleaned = _median_frame(frames, i)
                strips.append(cleaned[-new_rows_full:, :, :])
            prev_gray = curr_gray
            prev_idx = i
            step = _FRAME_STEP
            no_match_streak = 0
        else:
            prev_gray = curr_gray
            prev_idx = i
            step = min(step + _FRAME_STEP, 30)
            no_match_streak = 0

        i = prev_idx + step

    pages.append(np.vstack(strips))

    if len(pages) > 1:
        pages = _deduplicate_pages(pages)

    # LLM vision: crop each page to website content area
    if api_key:
        from .vision import detect_content_bbox, crop_to_content
        cropped_pages = []
        for page in pages:
            # Use the top portion of the page (first "frame" height) for detection
            bbox = detect_content_bbox(page, api_key)
            cropped_pages.append(crop_to_content(page, bbox))
        pages = cropped_pages

    return pages


def _deduplicate_pages(pages: list[np.ndarray]) -> list[np.ndarray]:
    """Remove single-frame pages that are visually similar to a neighbor."""
    from .similarity import _to_gray_thumbnail
    from skimage.metrics import structural_similarity

    if len(pages) <= 1:
        return pages

    result = []
    for i, page in enumerate(pages):
        single_frame = (page.shape[0] <= 1900)  # ~one cropped frame
        if not single_frame:
            result.append(page)
            continue

        # Check similarity with neighbors
        thumb = _to_gray_thumbnail(page)
        is_dup = False
        for j in [i - 1, i + 1]:
            if 0 <= j < len(pages):
                # Compare with top portion of neighbor (same size as this page)
                neighbor = pages[j]
                crop_h = min(page.shape[0], neighbor.shape[0])
                neighbor_top = neighbor[:crop_h]
                n_thumb = _to_gray_thumbnail(neighbor_top)
                if thumb.shape == n_thumb.shape:
                    s = structural_similarity(thumb, n_thumb)
                    if s > 0.85:
                        is_dup = True
                        break

        if not is_dup:
            result.append(page)

    return result
