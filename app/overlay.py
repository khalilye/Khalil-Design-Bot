# app/overlay.py
from io import BytesIO
from pathlib import Path

from PIL import Image


def apply_overlay_png(base_image_bytes: bytes, overlay_path: str) -> bytes:
    """
    يضع صورة PNG شفافة (كليشة) فوق صورة الأساس، ويعيد النتيجة كـ bytes.
    لو الملف غير موجود أو الطريق فاضي يرجع الصورة الأصلية كما هي.
    """
    if not overlay_path:
        return base_image_bytes

    overlay_file = Path(overlay_path)
    if not overlay_file.is_file():
        return base_image_bytes

    base_img = Image.open(BytesIO(base_image_bytes)).convert("RGBA")
    overlay_img = Image.open(overlay_file).convert("RGBA")

    overlay_img = overlay_img.resize(base_img.size, Image.LANCZOS)
    combined = Image.alpha_composite(base_img, overlay_img)

    out = BytesIO()
    combined.save(out, format="PNG")
    out.seek(0)
    return out.read()