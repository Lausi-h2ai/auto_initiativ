from __future__ import annotations

import base64
import io

import pytest
from PIL import Image

from backend.app.master_cv.contracts import FocalPoint, PortraitCrop
from backend.app.master_cv.portraits import PortraitService, PortraitValidationError


def _png_bytes(*, width: int = 80, height: int = 120) -> bytes:
    output = io.BytesIO()
    Image.new("RGBA", (width, height), (20, 80, 140, 180)).save(output, format="PNG")
    return output.getvalue()


def test_ingest_normalizes_to_application_owned_jpeg_without_metadata(tmp_path):
    service = PortraitService(tmp_path)
    crop = PortraitCrop(x=0.1, y=0.1, width=0.8, height=0.8)
    focal = FocalPoint(x=0.45, y=0.35)

    result = service.ingest(
        workspace_key="workspace_7",
        filename="../candidate.png",
        content=_png_bytes(),
        declared_mime_type="image/png",
        crop=crop,
        focal_point=focal,
    )

    stored = tmp_path / result.relative_path
    assert stored.is_file()
    assert result.original_filename == "candidate.png"
    assert result.mime_type == "image/jpeg"
    assert result.crop == crop
    assert result.focal_point == focal
    with Image.open(stored) as image:
        assert image.format == "JPEG"
        assert image.mode == "RGB"
        assert image.getexif() == {}

    uri = service.render_data_uri(relative_path=result.relative_path, expected_sha256=result.content_hash)
    assert uri.startswith("data:image/jpeg;base64,")
    assert base64.b64decode(uri.partition(",")[2]) == stored.read_bytes()

    cropped_uri = service.render_data_uri(
        relative_path=result.relative_path,
        expected_sha256=result.content_hash,
        crop=PortraitCrop(x=0, y=0, width=0.5, height=0.5),
    )
    with Image.open(io.BytesIO(base64.b64decode(cropped_uri.partition(",")[2]))) as cropped:
        assert cropped.size == (40, 60)


def test_ingest_rejects_declared_type_that_disagrees_with_content(tmp_path):
    with pytest.raises(PortraitValidationError, match="does not match"):
        PortraitService(tmp_path).ingest(
            workspace_key="workspace_1",
            filename="candidate.jpg",
            content=_png_bytes(),
            declared_mime_type="image/jpeg",
        )


def test_ingest_rejects_non_image_and_invalid_workspace(tmp_path):
    service = PortraitService(tmp_path)
    with pytest.raises(PortraitValidationError, match="not a valid"):
        service.ingest(workspace_key="workspace_1", filename="candidate.png", content=b"not an image")
    with pytest.raises(PortraitValidationError, match="workspace"):
        service.ingest(workspace_key="../other", filename="candidate.png", content=_png_bytes())


def test_render_rejects_unowned_path_and_tampering(tmp_path):
    service = PortraitService(tmp_path)
    result = service.ingest(workspace_key="workspace_1", filename="candidate.png", content=_png_bytes())

    with pytest.raises(PortraitValidationError, match="application-owned"):
        service.render_data_uri(relative_path="../secret.jpg", expected_sha256=result.content_hash)

    (tmp_path / result.relative_path).write_bytes(b"changed")
    with pytest.raises(PortraitValidationError, match="content hash"):
        service.render_data_uri(relative_path=result.relative_path, expected_sha256=result.content_hash)
