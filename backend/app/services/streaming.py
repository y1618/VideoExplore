import os
import re
from typing import Iterator

from fastapi import Request
from fastapi.responses import StreamingResponse

CHUNK_SIZE = 256 * 1024
RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")


def _parse_range(range_header: str, size: int) -> tuple[int, int] | None:
    match = RANGE_RE.match(range_header.strip())
    if not match:
        return None
    start_raw, end_raw = match.group(1), match.group(2)
    if start_raw == "" and end_raw == "":
        return None
    if start_raw == "":
        # suffix range: bytes=-N (末尾Nバイト)
        length = int(end_raw)
        if length <= 0:
            return None
        start = max(0, size - length)
        end = size - 1
    else:
        start = int(start_raw)
        end = int(end_raw) if end_raw else size - 1
    if start >= size:
        return None
    end = min(end, size - 1)
    if end < start:
        return None
    return start, end


def _iter_file(path: str, start: int, length: int) -> Iterator[bytes]:
    remaining = length
    with open(path, "rb") as f:
        f.seek(start)
        while remaining > 0:
            data = f.read(min(CHUNK_SIZE, remaining))
            if not data:
                break
            remaining -= len(data)
            yield data


def range_response(request: Request, path: str, content_type: str) -> StreamingResponse:
    """HTTP Range リクエスト対応のファイル配信(SMB マウント上の動画を想定)"""
    size = os.path.getsize(path)
    range_header = request.headers.get("range")
    status = 200
    start, end = 0, size - 1

    if range_header:
        parsed = _parse_range(range_header, size)
        if parsed is not None:
            start, end = parsed
            status = 206

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(end - start + 1),
        "Cache-Control": "no-cache",
    }
    if status == 206:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"

    return StreamingResponse(
        _iter_file(path, start, end - start + 1),
        status_code=status,
        headers=headers,
        media_type=content_type,
    )
