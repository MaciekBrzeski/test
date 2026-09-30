"""PDF object model and serialisation.

Python values map onto PDF objects as follows:

    None            -> null
    bool            -> true / false
    int, float      -> number
    str             -> literal string  (...)
    bytes           -> hex string      <...>
    Name            -> name            /Name
    list / tuple    -> array           [...]
    dict            -> dictionary      <<...>>   (keys are names)
    Ref             -> indirect ref    N 0 R
    Stream          -> stream object   (only valid as a top-level object)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = ["Name", "Ref", "Stream", "serialize"]


@dataclass(frozen=True)
class Name:
    value: str

    def to_bytes(self) -> bytes:
        out = bytearray(b"/")
        for ch in self.value.encode("latin-1"):
            # Delimiters, whitespace, '#' and non-printables must be escaped.
            if ch < 0x21 or ch > 0x7E or ch in b"#()<>[]{}/%":
                out += b"#%02X" % ch
            else:
                out.append(ch)
        return bytes(out)


@dataclass(frozen=True)
class Ref:
    num: int

    def to_bytes(self) -> bytes:
        return b"%d 0 R" % self.num


@dataclass
class Stream:
    dict: dict[str, Any] = field(default_factory=dict)
    data: bytes = b""


def _format_number(value: float) -> bytes:
    if isinstance(value, bool):
        raise TypeError("bool is not a PDF number")
    if isinstance(value, int):
        return b"%d" % value
    if value != value or value in (float("inf"), float("-inf")):
        raise ValueError(f"cannot serialise {value!r} as a PDF number")
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    if text in ("", "-0"):
        text = "0"
    return text.encode("ascii")


def _format_string(value: str) -> bytes:
    raw = value.encode("latin-1") if all(ord(c) < 256 for c in value) else (
        b"\xfe\xff" + value.encode("utf-16-be")
    )
    out = bytearray(b"(")
    for ch in raw:
        if ch in b"()\\":
            out += b"\\" + bytes([ch])
        elif ch == 0x0A:
            out += b"\\n"
        elif ch == 0x0D:
            out += b"\\r"
        else:
            out.append(ch)
    out += b")"
    return bytes(out)


def serialize(obj: Any) -> bytes:
    """Serialise a direct object (anything except a Stream)."""
    if obj is None:
        return b"null"
    if obj is True:
        return b"true"
    if obj is False:
        return b"false"
    if isinstance(obj, (int, float)):
        return _format_number(obj)
    if isinstance(obj, (Name, Ref)):
        return obj.to_bytes()
    if isinstance(obj, str):
        return _format_string(obj)
    if isinstance(obj, bytes):
        return b"<" + obj.hex().upper().encode("ascii") + b">"
    if isinstance(obj, (list, tuple)):
        return b"[" + b" ".join(serialize(item) for item in obj) + b"]"
    if isinstance(obj, dict):
        parts = [Name(key).to_bytes() + b" " + serialize(val) for key, val in obj.items()]
        return b"<<" + b" ".join(parts) + b">>"
    if isinstance(obj, Stream):
        raise TypeError("streams must be top-level indirect objects")
    raise TypeError(f"cannot serialise {type(obj).__name__} as a PDF object")
