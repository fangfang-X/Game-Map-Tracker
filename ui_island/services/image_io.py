"""OpenCV image IO helpers that work with non-ASCII Windows paths."""

from __future__ import annotations

import os

import cv2
import numpy as np


def imread_unicode(path: str | os.PathLike[str] | None, flags: int = cv2.IMREAD_COLOR) -> np.ndarray | None:
    """Read an image using a Unicode-safe path flow."""
    if path is None:
        return None
    try:
        buffer = np.fromfile(os.fspath(path), dtype=np.uint8)
    except (OSError, ValueError):
        return None
    if buffer.size <= 0:
        return None
    try:
        return cv2.imdecode(buffer, flags)
    except cv2.error:
        return None
