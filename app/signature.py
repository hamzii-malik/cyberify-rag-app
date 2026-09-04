"""Utilities for validating and storing e-signature PNG images."""

import base64
import binascii
from pathlib import Path
from uuid import uuid4

from PIL import Image


class SignatureError(ValueError):
    """Raised when submitted signature data is not a valid PNG image."""


def save_signature(data_url: str, upload_dir: Path) -> tuple[Path, str]:
    """Validate a PNG data URL and save it in the uploads directory."""
    if not data_url.startswith("data:image/png;base64,"):
        raise SignatureError("Signature must be a PNG data URL")

    encoded = data_url.split(",", 1)[1]
    try:
        image_bytes = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as error:
        raise SignatureError("Signature contains invalid base64 data") from error

    try:
        from io import BytesIO

        with Image.open(BytesIO(image_bytes)) as image:
            if image.format != "PNG":
                raise SignatureError("Signature must be a PNG image")
            image.verify()

        # Remove transparent canvas margins so the document image fits the ink.
        with Image.open(BytesIO(image_bytes)) as image:
            rgba_image = image.convert("RGBA")
            alpha_box = rgba_image.getchannel("A").getbbox()
            if alpha_box:
                output = BytesIO()
                rgba_image.crop(alpha_box).save(output, format="PNG")
                image_bytes = output.getvalue()
    except SignatureError:
        raise
    except Exception as error:
        raise SignatureError("Signature is not a valid PNG image") from error

    upload_dir.mkdir(exist_ok=True, parents=True)
    filename = f"sig-{uuid4().hex[:12]}.png"
    signature_path = upload_dir / filename
    signature_path.write_bytes(image_bytes)
    return signature_path, filename
