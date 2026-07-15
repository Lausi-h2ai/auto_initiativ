from __future__ import annotations

import base64
import hashlib
import io
import re
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError

from backend.app.master_cv.contracts import FocalPoint, PortraitCrop


MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_SOURCE_DIMENSION = 12_000
MAX_SOURCE_PIXELS = 50_000_000
MAX_NORMALIZED_DIMENSION = 2_400
ALLOWED_FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
WORKSPACE_SEGMENT = re.compile(r"^[A-Za-z0-9_-]{1,100}$")


class PortraitValidationError(ValueError):
    pass


@dataclass(frozen=True)
class PortraitIngestResult:
    asset_id: str
    original_filename: str
    mime_type: str
    relative_path: str
    content_hash: str
    size_bytes: int
    width: int
    height: int
    crop: PortraitCrop
    focal_point: FocalPoint


class PortraitService:
    """Owns sanitized portrait files; callers persist only returned metadata."""

    def __init__(self, storage_root: Path) -> None:
        self.storage_root = storage_root.resolve()

    def ingest(
        self,
        *,
        workspace_key: str,
        filename: str,
        content: bytes,
        declared_mime_type: str | None = None,
        crop: PortraitCrop | None = None,
        focal_point: FocalPoint | None = None,
    ) -> PortraitIngestResult:
        if not WORKSPACE_SEGMENT.fullmatch(workspace_key):
            raise PortraitValidationError("invalid workspace key")
        if not content:
            raise PortraitValidationError("portrait is empty")
        if len(content) > MAX_UPLOAD_BYTES:
            raise PortraitValidationError("portrait exceeds 10 MB")

        try:
            with Image.open(io.BytesIO(content)) as probe:
                actual_format = probe.format
                width, height = probe.size
                probe.verify()
        except (UnidentifiedImageError, OSError, SyntaxError) as exc:
            raise PortraitValidationError("portrait is not a valid JPEG, PNG, or WebP image") from exc

        actual_mime = ALLOWED_FORMATS.get(actual_format or "")
        if actual_mime is None:
            raise PortraitValidationError("portrait format must be JPEG, PNG, or WebP")
        if declared_mime_type and declared_mime_type.lower() != actual_mime:
            raise PortraitValidationError("declared portrait MIME type does not match its content")
        if width < 1 or height < 1 or width > MAX_SOURCE_DIMENSION or height > MAX_SOURCE_DIMENSION:
            raise PortraitValidationError("portrait dimensions are outside the supported range")
        if width * height > MAX_SOURCE_PIXELS:
            raise PortraitValidationError("portrait has too many pixels")

        try:
            with Image.open(io.BytesIO(content)) as source:
                normalized = ImageOps.exif_transpose(source)
                embedded_profile = normalized.info.get("icc_profile")
                if embedded_profile:
                    try:
                        normalized = ImageCms.profileToProfile(
                            normalized,
                            ImageCms.ImageCmsProfile(io.BytesIO(embedded_profile)),
                            ImageCms.createProfile("sRGB"),
                            outputMode="RGB",
                        )
                    except (OSError, ValueError) as exc:
                        raise PortraitValidationError("portrait has an invalid color profile") from exc
                normalized.thumbnail((MAX_NORMALIZED_DIMENSION, MAX_NORMALIZED_DIMENSION), Image.Resampling.LANCZOS)
                if normalized.mode != "RGB":
                    background = Image.new("RGB", normalized.size, "white")
                    if "A" in normalized.getbands():
                        background.paste(normalized, mask=normalized.getchannel("A"))
                    else:
                        background.paste(normalized.convert("RGB"))
                    normalized = background
                else:
                    normalized = normalized.copy()
                output = io.BytesIO()
                normalized.save(output, format="JPEG", quality=90, optimize=True, progressive=True)
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise PortraitValidationError("portrait could not be normalized safely") from exc

        normalized_bytes = output.getvalue()
        asset_id = f"portrait_{uuid4().hex}"
        relative = Path(workspace_key) / "profile_assets" / f"{asset_id}.jpg"
        destination = self._resolve_relative(relative.as_posix())
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(".tmp")
        temporary.write_bytes(normalized_bytes)
        temporary.replace(destination)

        selected_crop = crop or PortraitCrop(x=0, y=0, width=1, height=1)
        selected_focal = focal_point or FocalPoint()
        return PortraitIngestResult(
            asset_id=asset_id,
            original_filename=Path(filename).name[:255] or "portrait",
            mime_type="image/jpeg",
            relative_path=relative.as_posix(),
            content_hash=hashlib.sha256(normalized_bytes).hexdigest(),
            size_bytes=len(normalized_bytes),
            width=normalized.width,
            height=normalized.height,
            crop=selected_crop,
            focal_point=selected_focal,
        )

    def render_data_uri(
        self,
        *,
        relative_path: str,
        expected_sha256: str,
        crop: PortraitCrop | None = None,
        max_dimension: int = 1_200,
    ) -> str:
        """Read an application-owned normalized JPEG and verify it before rendering."""
        if not re.fullmatch(r"[A-Za-z0-9_-]+/profile_assets/portrait_[0-9a-f]{32}\.jpg", relative_path):
            raise PortraitValidationError("portrait path is not application-owned")
        path = self._resolve_relative(relative_path)
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise PortraitValidationError("portrait file is unavailable") from exc
        if hashlib.sha256(content).hexdigest() != expected_sha256:
            raise PortraitValidationError("portrait content hash does not match persisted metadata")
        try:
            with Image.open(io.BytesIO(content)) as image:
                if image.format != "JPEG":
                    raise PortraitValidationError("stored portrait is not a normalized JPEG")
                image.verify()
        except (UnidentifiedImageError, OSError, SyntaxError) as exc:
            raise PortraitValidationError("stored portrait is invalid") from exc
        render_bytes = content
        if crop is not None:
            with Image.open(io.BytesIO(content)) as source:
                left = round(source.width * crop.x)
                top = round(source.height * crop.y)
                right = round(source.width * (crop.x + crop.width))
                bottom = round(source.height * (crop.y + crop.height))
                variant = source.crop((left, top, right, bottom))
                bounded_dimension = max(64, min(max_dimension, MAX_NORMALIZED_DIMENSION))
                variant.thumbnail((bounded_dimension, bounded_dimension), Image.Resampling.LANCZOS)
                output = io.BytesIO()
                variant.save(output, format="JPEG", quality=90, optimize=True, progressive=True)
                render_bytes = output.getvalue()
        return "data:image/jpeg;base64," + base64.b64encode(render_bytes).decode("ascii")

    def _resolve_relative(self, relative_path: str) -> Path:
        candidate = (self.storage_root / Path(relative_path)).resolve()
        if candidate == self.storage_root or self.storage_root not in candidate.parents:
            raise PortraitValidationError("portrait path escapes storage root")
        return candidate
