"""Decode and encode protocol buffers from hand-written schemas.

Parsers for agents that store protobuf need no generated code and no
third-party package.

A schema is a dict: message name -> {field number: (field name, kind)} where
kind is one of 'str', 'bytes', 'int', 'bool', 'float', 'double', 'ts'
(google.protobuf.Timestamp, decoded to a UTC string), or another message
name for a nested message. Prefix the field name with '+' for a repeated
field (packed scalars are handled). Unknown fields are skipped, so a schema
only needs the fields a parser reads.
"""

from __future__ import annotations

import struct
from collections.abc import Iterator
from typing import Any

from .timeutil import to_utc

Schema = dict[str, dict[int, tuple[str, str]]]

SCALARS = ("str", "bytes", "int", "bool", "float", "double", "ts")


def read_varint(data: bytes, offset: int) -> tuple[int, int]:
    """Return the varint at `offset` and the offset after it.

    Raises:
        ValueError: The varint is cut off or too long.
    """
    result = 0
    shift = 0
    while True:
        if offset >= len(data):
            raise ValueError("truncated varint")
        byte = data[offset]
        offset += 1
        result |= (byte & 0x7F) << shift
        shift += 7
        if not byte & 0x80:
            return result, offset
        if shift > 70:
            raise ValueError("varint too long")


def iter_fields(data: bytes) -> Iterator[tuple[int, int, Any]]:
    """Yield (field_number, wire_type, value) for each field on the wire.

    Length-delimited values are bytes, varints int, fixed widths raw bytes.
    The value is typed Any because its type follows the wire type.

    Raises:
        ValueError: The buffer is cut off or holds an unsupported wire type.
    """
    offset = 0
    size = len(data)
    while offset < size:
        tag, offset = read_varint(data, offset)
        field = tag >> 3
        wire_type = tag & 7
        if wire_type == 0:
            value, offset = read_varint(data, offset)
            yield field, wire_type, value
        elif wire_type == 1:
            yield field, wire_type, data[offset : offset + 8]
            offset += 8
        elif wire_type == 5:
            yield field, wire_type, data[offset : offset + 4]
            offset += 4
        elif wire_type == 2:
            length, offset = read_varint(data, offset)
            if length > size - offset:
                raise ValueError("truncated length-delimited field")
            yield field, wire_type, data[offset : offset + length]
            offset += length
        else:
            raise ValueError("unsupported wire type %d" % wire_type)


def _timestamp(data: bytes) -> str:
    seconds = 0
    nanos = 0
    for number, wire_type, value in iter_fields(data):
        if number == 1 and wire_type == 0:
            seconds = value
        elif number == 2 and wire_type == 0:
            nanos = value
    if not seconds:
        return ""
    return to_utc(seconds + nanos / 1e9)


def _scalar(kind: str, wire_type: int, value) -> Any:
    if kind == "str":
        return value.decode("utf-8", "replace") if isinstance(value, bytes) else str(value)
    if kind == "bytes":
        return value if isinstance(value, bytes) else b""
    if kind == "int":
        if isinstance(value, bytes):
            return (
                struct.unpack("<q", value)[0] if len(value) == 8 else struct.unpack("<i", value)[0]
            )
        return value
    if kind == "bool":
        return bool(value)
    if kind == "float":
        return (
            struct.unpack("<f", value)[0]
            if isinstance(value, bytes) and len(value) == 4
            else float(value)
        )
    if kind == "double":
        return (
            struct.unpack("<d", value)[0]
            if isinstance(value, bytes) and len(value) == 8
            else float(value)
        )
    if kind == "ts":
        return _timestamp(value) if isinstance(value, bytes) else to_utc(value)
    raise ValueError(kind)


def decode(data: bytes, message: str, schema: Schema) -> dict[str, Any]:
    """Decode bytes as `message` per `schema`.

    Unknown fields are skipped.

    Returns:
        The fields present, by name; a repeated field is a list.

    Raises:
        ValueError: The buffer is malformed.
    """
    fields = schema[message]
    out: dict[str, Any] = {}
    for number, wire_type, value in iter_fields(data):
        spec = fields.get(number)
        if spec is None:
            continue
        name, kind = spec
        repeated = name.startswith("+")
        if repeated:
            name = name[1:]
        if kind in SCALARS:
            if repeated and kind in ("int", "bool") and wire_type == 2 and isinstance(value, bytes):
                values = []
                offset = 0
                while offset < len(value):
                    item, offset = read_varint(value, offset)
                    values.append(bool(item) if kind == "bool" else item)
                out.setdefault(name, []).extend(values)
                continue
            try:
                decoded = _scalar(kind, wire_type, value)
            except (struct.error, ValueError):
                continue
        else:
            if not isinstance(value, bytes):
                continue
            try:
                decoded = decode(value, kind, schema)
            except ValueError:
                continue
        if repeated:
            out.setdefault(name, []).append(decoded)
        else:
            out[name] = decoded
    return out


# ---- encoder, used by the tests to build fixtures -------------------------


def _write_varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _tag(field: int, wire_type: int) -> bytes:
    return _write_varint((field << 3) | wire_type)


def _encode_scalar(field: int, kind: str, value) -> bytes:
    if kind == "str":
        data = str(value).encode("utf-8")
        return _tag(field, 2) + _write_varint(len(data)) + data
    if kind == "bytes":
        return _tag(field, 2) + _write_varint(len(value)) + bytes(value)
    if kind in ("int", "bool"):
        return _tag(field, 0) + _write_varint(int(value) & 0xFFFFFFFFFFFFFFFF)
    if kind == "float":
        return _tag(field, 5) + struct.pack("<f", value)
    if kind == "double":
        return _tag(field, 1) + struct.pack("<d", value)
    if kind == "ts":
        # Epoch seconds, a fraction allowed.
        seconds = int(value)
        nanos = round((value - seconds) * 1e9)
        body = _tag(1, 0) + _write_varint(seconds)
        if nanos:
            body += _tag(2, 0) + _write_varint(nanos)
        return _tag(field, 2) + _write_varint(len(body)) + body
    raise ValueError(kind)


def encode(values: dict[str, Any], message: str, schema: Schema) -> bytes:
    """Encode a dict as `message` per `schema`; a repeated field takes a list."""
    by_name = {}
    for number, (name, kind) in schema[message].items():
        by_name[name.lstrip("+")] = (number, kind, name.startswith("+"))
    out = bytearray()
    for name, value in values.items():
        number, kind, repeated = by_name[name]
        items = value if repeated else [value]
        for item in items:
            if kind in SCALARS:
                out += _encode_scalar(number, kind, item)
            else:
                body = encode(item, kind, schema)
                out += _tag(number, 2) + _write_varint(len(body)) + body
    return bytes(out)
