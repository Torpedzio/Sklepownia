"""Profile pictures: whatever the user uploads is stored as one small square WebP."""

import uuid
from io import BytesIO

from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
# A small file can still unpack into a huge bitmap; refuse those before decoding.
MAX_PIXELS = 40_000_000
SIZE = 512
FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}


class InvalidAvatar(ValueError):
    pass


def process_avatar(upload) -> ContentFile:
    """Crops the picture to a centred square, scales it to SIZE and drops its metadata (EXIF, GPS)."""
    if upload.size > MAX_UPLOAD_BYTES:
        raise InvalidAvatar("Zdjęcie jest za duże. Wybierz plik do 10 MB.")
    try:
        image = Image.open(upload)
        if image.format not in FORMATS:
            raise InvalidAvatar("Wybierz zdjęcie JPG, PNG, WebP albo GIF.")
        if image.width * image.height > MAX_PIXELS:
            raise InvalidAvatar("Zdjęcie ma za dużą rozdzielczość.")
        image.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise InvalidAvatar("To nie jest zdjęcie albo plik jest uszkodzony.") from None

    # Phones store the rotation in EXIF; apply it before the metadata is dropped.
    image = ImageOps.exif_transpose(image)
    image = image.convert("RGBA" if _has_alpha(image) else "RGB")
    image = ImageOps.fit(image, (SIZE, SIZE), Image.Resampling.LANCZOS)

    output = BytesIO()
    image.save(output, "WEBP", quality=85, method=4)
    # A fresh name for every picture, so it can be cached for good and old links stop working.
    return ContentFile(output.getvalue(), name=f"{uuid.uuid4().hex}.webp")


def _has_alpha(image) -> bool:
    return image.mode in ("RGBA", "LA", "PA") or (image.mode == "P" and "transparency" in image.info)
