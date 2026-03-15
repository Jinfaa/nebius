"""Video frame extraction using PyAV."""

from pathlib import Path
from typing import Generator

import av
import numpy as np


def iter_frames(video_path: Path) -> Generator[tuple[int, np.ndarray], None, None]:
    """
    Iterate over video frames as numpy arrays in RGB format.

    Yields:
        (frame_index, rgb_array) tuples where rgb_array is shape (height, width, 3)
    """
    container = av.open(str(video_path))

    for frame_index, frame in enumerate(container.decode(video=0)):
        rgb_array = frame.to_ndarray(format="rgb24")
        yield frame_index, rgb_array
