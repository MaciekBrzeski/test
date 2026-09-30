"""Minimal, dependency-free PDF file writer.

The writer holds a table of indirect objects and emits a classic
(non-incremental) PDF 1.7 file with a cross-reference table. Output is
deterministic: the same objects always produce the same bytes.
"""

from __future__ import annotations

import hashlib
from typing import Any, BinaryIO

from .objects import Ref, Stream, serialize

__all__ = ["PdfWriter"]

_HEADER = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n"


class PdfWriter:
    def __init__(self) -> None:
        self._objects: list[Any] = []

    def reserve(self) -> Ref:
        """Allocate an object number now and fill it in later with `set`."""
        self._objects.append(None)
        return Ref(len(self._objects))

    def set(self, ref: Ref, obj: Any) -> None:
        self._objects[ref.num - 1] = obj

    def add(self, obj: Any) -> Ref:
        ref = self.reserve()
        self.set(ref, obj)
        return ref

    def write(self, fp: BinaryIO, root: Ref, info: Ref | None = None) -> None:
        offsets: list[int] = []
        pos = 0

        def emit(chunk: bytes) -> None:
            nonlocal pos
            fp.write(chunk)
            pos += len(chunk)

        emit(_HEADER)
        digest = hashlib.md5()
        for num, obj in enumerate(self._objects, start=1):
            if obj is None:
                raise ValueError(f"object {num} was reserved but never set")
            offsets.append(pos)
            body = self._serialize_indirect(obj)
            digest.update(body)
            emit(b"%d 0 obj\n" % num + body + b"\nendobj\n")

        xref_pos = pos
        count = len(self._objects) + 1
        emit(b"xref\n0 %d\n" % count)
        emit(b"0000000000 65535 f \n")
        for offset in offsets:
            emit(b"%010d 00000 n \n" % offset)

        # A content-derived file ID keeps output reproducible.
        file_id = digest.digest()
        trailer: dict[str, Any] = {"Size": count, "Root": root, "ID": [file_id, file_id]}
        if info is not None:
            trailer["Info"] = info
        emit(b"trailer\n" + serialize(trailer) + b"\n")
        emit(b"startxref\n%d\n%%%%EOF\n" % xref_pos)

    @staticmethod
    def _serialize_indirect(obj: Any) -> bytes:
        if isinstance(obj, Stream):
            header = dict(obj.dict)
            header["Length"] = len(obj.data)
            return serialize(header) + b"\nstream\n" + obj.data + b"\nendstream"
        return serialize(obj)
