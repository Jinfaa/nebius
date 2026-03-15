"""LLM vision: detect website content bounding box in a screenshot frame."""

import base64
import io
import json

import numpy as np
from openai import OpenAI
from PIL import Image

_NEBIUS_BASE_URL = "https://api.studio.nebius.com/v1/"
_MODEL = "Qwen/Qwen2.5-VL-72B-Instruct"


def _frame_to_base64(frame: np.ndarray, max_dim: int = 1024) -> str:
    """Downscale frame and encode as base64 JPEG for API."""
    img = Image.fromarray(frame)
    scale = max_dim / max(img.size)
    if scale < 1.0:
        img = img.resize(
            (int(img.width * scale), int(img.height * scale)),
            Image.Resampling.BILINEAR,
        )
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=80)
    return base64.b64encode(buf.getvalue()).decode()


def detect_content_bbox(
    frame: np.ndarray,
    api_key: str,
) -> tuple[int, int, int, int]:
    """
    Use vision LLM to detect the website content area in a screenshot.

    Returns (top, bottom, left, right) in original frame pixel coordinates.
    """
    h, w = frame.shape[:2]

    # Downscale for API, remember scale factor
    max_dim = 1024
    scale = max_dim / max(w, h)
    if scale >= 1.0:
        scale = 1.0

    b64 = _frame_to_base64(frame, max_dim)

    client = OpenAI(base_url=_NEBIUS_BASE_URL, api_key=api_key)

    response = client.chat.completions.create(
        model=_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{b64}",
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            "This is a screenshot of a computer screen. "
                            "Find the exact bounding box of the WEBSITE CONTENT AREA only. "
                            "Exclude: OS menu bar, browser tabs, browser URL bar, "
                            "OS dock/taskbar, desktop background, any system UI. "
                            "Include: the website's own navigation bar, main content, footer. "
                            "Return ONLY a JSON object with pixel coordinates relative to this image: "
                            '{"top": N, "bottom": N, "left": N, "right": N} '
                            "No explanation, just the JSON."
                        ),
                    },
                ],
            }
        ],
        max_tokens=100,
        temperature=0.0,
    )

    text = response.choices[0].message.content.strip()

    # Parse JSON from response (handle markdown code blocks)
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    bbox = json.loads(text)

    # Scale coordinates back to original frame size
    scale_inv = 1.0 / scale if scale < 1.0 else 1.0
    top = max(0, int(bbox["top"] * scale_inv))
    bottom = min(h, int(bbox["bottom"] * scale_inv))
    left = max(0, int(bbox["left"] * scale_inv))
    right = min(w, int(bbox["right"] * scale_inv))

    return top, bottom, left, right


def crop_to_content(frame: np.ndarray, bbox: tuple[int, int, int, int]) -> np.ndarray:
    """Crop frame to content bounding box."""
    top, bottom, left, right = bbox
    return frame[top:bottom, left:right, :]
