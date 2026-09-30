"""Tiny lossless PNG writer, used to export frames for previews and debugging."""

from __future__ import annotations

import os
import struct
import zlib
from typing import Union

import numpy as np

from ..pdf.image import png_filter

__all__ = ["encode_png", "save_png"]

_COLOR_TYPES = {1: 0, 3: 2, 4: 6}  # gray, RGB, RGBA


def encode_png(pixels: np.ndarray, level: int = 6) -> bytes:
    if pixels.dtype != np.uint8:
        raise TypeError(f"expected uint8 pixels, got {pixels.dtype}")
    if pixels.ndim == 2:
        pixels = pixels[:, :, np.newaxis]
    height, width, channels = pixels.shape
    if height == 0 or width == 0:
        raise ValueError("image must be at least 1x1")
    if channels not in _COLOR_TYPES:
        raise ValueError(f"cannot write {channels}-channel PNG")
    rows = np.ascontiguousarray(pixels).reshape(height, width * channels)
    header = struct.pack(">IIBBBBB", width, height, 8, _COLOR_TYPES[channels], 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n"
            + _chunk(b"IHDR", header)
            + _chunk(b"IDAT", zlib.compress(png_filter(rows, channels), level))
            + _chunk(b"IEND", b""))


def save_png(path: Union[str, os.PathLike], pixels: np.ndarray, level: int = 6) -> None:
    with open(path, "wb") as fp:
        fp.write(encode_png(pixels, level))


def _chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))
