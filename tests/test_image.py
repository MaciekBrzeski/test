import io

import numpy as np
import pytest

from pixelpdf.pdf.image import encode_image
from pixelpdf.pdf.objects import Name
from pixelpdf.pdf.writer import PdfWriter

pikepdf = pytest.importorskip("pikepdf")


def decode_with_qpdf(pixels: np.ndarray, **kwargs) -> np.ndarray:
    """Embed the encoded stream in a PDF and decode it with qpdf (independent decoder)."""
    w = PdfWriter()
    pages = w.reserve()
    image = w.add(encode_image(pixels, **kwargs))
    page = w.add({"Type": Name("Page"), "Parent": pages, "MediaBox": [0, 0, 1, 1],
                  "Resources": {"XObject": {"Im0": image}}})
    w.set(pages, {"Type": Name("Pages"), "Kids": [page], "Count": 1})
    root = w.add({"Type": Name("Catalog"), "Pages": pages})
    buf = io.BytesIO()
    w.write(buf, root)
    with pikepdf.open(io.BytesIO(buf.getvalue())) as pdf:
        obj = pdf.pages[0].Resources.XObject.Im0
        data = obj.read_bytes()
    channels = 1 if pixels.ndim == 2 else pixels.shape[2]
    return np.frombuffer(data, dtype=np.uint8).reshape(pixels.shape[0], pixels.shape[1], channels)


def gradient(h, w, c):
    y, x = np.mgrid[0:h, 0:w]
    planes = [(x * 255 // max(w - 1, 1)), (y * 255 // max(h - 1, 1)), ((x + y) % 256), (x ^ y) % 256]
    return np.stack(planes[:c], axis=2).astype(np.uint8)


@pytest.mark.parametrize("shape", [(1, 1, 3), (1, 7, 3), (9, 1, 3), (300, 257, 3),
                                   (40, 33, 1), (17, 21, 4)])
@pytest.mark.parametrize("kind", ["random", "gradient"])
@pytest.mark.parametrize("predict", [True, False])
def test_lossless_roundtrip(rng, shape, kind, predict):
    if kind == "random":
        pixels = rng.integers(0, 256, shape, dtype=np.uint8)
    else:
        pixels = gradient(*shape)
    decoded = decode_with_qpdf(pixels, predict=predict)
    np.testing.assert_array_equal(decoded, pixels)


def test_grayscale_2d_array(rng):
    pixels = rng.integers(0, 256, (20, 30), dtype=np.uint8)
    decoded = decode_with_qpdf(pixels)
    np.testing.assert_array_equal(decoded[:, :, 0], pixels)


def test_roundtrip_spans_multiple_prediction_chunks(rng):
    # Taller than the internal 256-row chunk so rows at chunk seams are exercised.
    pixels = gradient(600, 50, 3)
    pixels[::7] = rng.integers(0, 256, pixels[::7].shape, dtype=np.uint8)
    np.testing.assert_array_equal(decode_with_qpdf(pixels), pixels)


def test_header():
    stream = encode_image(np.zeros((5, 8, 3), dtype=np.uint8))
    assert stream.dict["Width"] == 8
    assert stream.dict["Height"] == 5
    assert stream.dict["ColorSpace"] == Name("DeviceRGB")
    assert stream.dict["Interpolate"] is False


def test_prediction_helps_smooth_images():
    pixels = gradient(400, 400, 3)
    assert len(encode_image(pixels).data) < len(encode_image(pixels, predict=False).data)


@pytest.mark.parametrize("bad", [np.zeros((4, 4, 3), dtype=np.float32),
                                 np.zeros((4, 4, 2), dtype=np.uint8),
                                 np.zeros((0, 4, 3), dtype=np.uint8)])
def test_rejects_bad_input(bad):
    with pytest.raises((TypeError, ValueError)):
        encode_image(bad)
