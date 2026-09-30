"""Lossless encoding of pixel arrays as PDF image XObjects.

Pixels are compressed with Flate (zlib) after PNG row prediction, which
the PDF spec supports natively via /DecodeParms /Predictor 15. Each row
gets whichever of the five PNG filters (None, Sub, Up, Average, Paeth)
yields the smallest sum of absolute residuals — the same heuristic
libpng uses — so the decoded samples are bit-for-bit identical to the
input while typically compressing far better than raw Flate.
"""

from __future__ import annotations

import zlib

import numpy as np

from .objects import Name, Stream

__all__ = ["encode_image", "png_filter"]

_COLOR_SPACES = {1: "DeviceGray", 3: "DeviceRGB", 4: "DeviceCMYK"}


def encode_image(pixels: np.ndarray, *, level: int = 6, predict: bool = True) -> Stream:
    """Encode an (H, W) or (H, W, C) uint8 array as an image XObject stream."""
    if pixels.dtype != np.uint8:
        raise TypeError(f"expected uint8 pixels, got {pixels.dtype}")
    if pixels.ndim == 2:
        pixels = pixels[:, :, np.newaxis]
    if pixels.ndim != 3 or pixels.shape[2] not in _COLOR_SPACES:
        raise ValueError(f"unsupported pixel array shape {pixels.shape}")
    height, width, channels = pixels.shape
    if height == 0 or width == 0:
        raise ValueError("image must be at least 1x1")

    header = {
        "Type": Name("XObject"),
        "Subtype": Name("Image"),
        "Width": width,
        "Height": height,
        "ColorSpace": Name(_COLOR_SPACES[channels]),
        "BitsPerComponent": 8,
        "Interpolate": False,
        "Filter": Name("FlateDecode"),
    }
    rows = np.ascontiguousarray(pixels).reshape(height, width * channels)
    if predict:
        payload = png_filter(rows, channels)
        header["DecodeParms"] = {
            "Predictor": 15,
            "Colors": channels,
            "BitsPerComponent": 8,
            "Columns": width,
        }
    else:
        payload = rows.tobytes()
    return Stream(header, zlib.compress(payload, level))


_CHUNK_ROWS = 256  # bounds temporary memory on large (e.g. 300 DPI A4) images


def png_filter(rows: np.ndarray, bpp: int) -> bytes:
    """Apply per-row adaptive PNG filtering; returns filter-byte-prefixed rows."""
    out = []
    prev = np.zeros((1, rows.shape[1]), dtype=np.uint8)
    for start in range(0, len(rows), _CHUNK_ROWS):
        chunk = rows[start : start + _CHUNK_ROWS]
        out.append(_png_predict_chunk(chunk, prev, bpp))
        prev = chunk[-1:]
    return b"".join(out)


def _png_predict_chunk(rows: np.ndarray, prev: np.ndarray, bpp: int) -> bytes:
    """Filter `rows`, where `prev` is the (unfiltered) row just above them."""
    x = rows.astype(np.int16)
    a = np.zeros_like(x)  # left
    a[:, bpp:] = x[:, :-bpp]
    above = np.concatenate([prev.astype(np.int16), x[:-1]])
    b = above  # up
    c = np.zeros_like(x)  # up-left
    c[:, bpp:] = above[:, :-bpp]

    p = a + b - c
    pa, pb, pc = np.abs(p - a), np.abs(p - b), np.abs(p - c)
    paeth = np.where((pa <= pb) & (pa <= pc), a, np.where(pb <= pc, b, c))

    predictions = (None, a, b, (a + b) // 2, paeth)
    best_rows = x.astype(np.uint8)
    best_type = np.zeros(len(x), dtype=np.uint8)
    best_score = np.abs(best_rows.view(np.int8).astype(np.int32)).sum(axis=1)
    for ftype in range(1, 5):
        filtered = (x - predictions[ftype]).astype(np.uint8)
        score = np.abs(filtered.view(np.int8).astype(np.int32)).sum(axis=1)
        better = score < best_score
        if better.any():
            best_rows[better] = filtered[better]
            best_type[better] = ftype
            best_score[better] = score[better]

    return np.concatenate([best_type[:, np.newaxis], best_rows], axis=1).tobytes()
