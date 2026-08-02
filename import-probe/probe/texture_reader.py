from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass

from PIL import Image, UnidentifiedImageError

from .errors import ProbeReject


@dataclass(frozen=True)
class TextureFacts:
    content_sha256: str
    decoded_pixel_sha256: str
    width: int
    height: int
    mode: str


def decode_png(data: bytes) -> TextureFacts:
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            rgba = image.convert("RGBA")
            pixels = rgba.tobytes()
            width, height = rgba.size
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ProbeReject("texture_decode", "PNG texture could not be decoded safely") from exc
    return TextureFacts(
        content_sha256=hashlib.sha256(data).hexdigest(),
        decoded_pixel_sha256=hashlib.sha256(pixels).hexdigest(),
        width=width,
        height=height,
        mode="RGBA",
    )
