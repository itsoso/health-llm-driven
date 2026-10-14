"""Preview requests must retain the original private-image authorization boundary."""
import io
import time

import pytest
from PIL import Image


def photo_bytes(size=(1600, 1200), color="orange"):
    output = io.BytesIO()
    Image.new("RGB", size, color).save(output, format="JPEG", quality=95)
    return output.getvalue()


@pytest.mark.parametrize("category", ["diet", "chat"])
def test_preview_is_smaller_and_original_remains_unchanged(
    client, auth_user_and_headers, tmp_path, monkeypatch, category,
):
    from app.api import upload
    from app.services.private_uploads import build_signed_private_upload_url

    owner, headers = auth_user_and_headers
    monkeypatch.setattr(upload, "UPLOAD_DIR", str(tmp_path))
    file = tmp_path / category / str(owner.id) / "photo.jpg"
    file.parent.mkdir(parents=True)
    original = photo_bytes()
    file.write_bytes(original)
    url = build_signed_private_upload_url(category, owner.id, file.name)
    response = client.get(url + "&variant=preview")
    assert response.status_code == 200
    assert len(response.content) < len(original)
    assert max(Image.open(io.BytesIO(response.content)).size) <= 960
    assert response.headers["cache-control"] == "private, no-store"
    assert client.get(url).content == original
    # Warming the derivative must not bypass authentication or file deletion.
    unsigned = url.split("?")[0] + "?variant=preview"
    assert client.get(unsigned).status_code == 401
    assert client.get(unsigned, headers=headers).status_code == 200
    expired = build_signed_private_upload_url(category, owner.id, file.name, expires=int(time.time()) - 1)
    assert client.get(expired + "&variant=preview").status_code == 401
    file.unlink()
    assert client.get(url + "&variant=preview").status_code == 404


def test_preview_rejects_other_owner(client, db, auth_user_and_headers, tmp_path, monkeypatch):
    from app.api import upload
    from tests.conftest import create_authenticated_user

    owner, _ = auth_user_and_headers
    _, token = create_authenticated_user(db)
    monkeypatch.setattr(upload, "UPLOAD_DIR", str(tmp_path))
    file = tmp_path / "diet" / str(owner.id) / "photo.jpg"
    file.parent.mkdir(parents=True)
    file.write_bytes(photo_bytes())
    response = client.get(f"/api/v1/upload/files/diet/{owner.id}/photo.jpg?variant=preview",
                          headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403


def test_preview_legacy_requires_capability(client, tmp_path, monkeypatch):
    from app.api import upload
    from app.services.private_uploads import build_signed_private_upload_url

    monkeypatch.setattr(upload, "UPLOAD_DIR", str(tmp_path))
    file = tmp_path / "diet" / "legacy.jpg"
    file.parent.mkdir()
    file.write_bytes(photo_bytes())
    url = build_signed_private_upload_url("diet", 71, file.name, legacy=True)
    response = client.get(url + "&variant=preview")
    assert response.status_code == 200
    assert max(Image.open(io.BytesIO(response.content)).size) <= 960
    assert client.get(url.split("?")[0] + "?variant=preview").status_code == 401


def test_preview_rejects_corrupt_image(client, auth_user_and_headers, tmp_path, monkeypatch):
    from app.api import upload

    owner, headers = auth_user_and_headers
    monkeypatch.setattr(upload, "UPLOAD_DIR", str(tmp_path))
    file = tmp_path / "diet" / str(owner.id) / "photo.jpg"
    file.parent.mkdir(parents=True)
    file.write_bytes(b"not an image")
    response = client.get(f"/api/v1/upload/files/diet/{owner.id}/photo.jpg?variant=preview", headers=headers)
    assert response.status_code == 422


def test_preview_cache_invalidates_when_source_changes(tmp_path):
    from app.utils.private_image_preview import load_preview

    file = tmp_path / "photo.jpg"
    file.write_bytes(photo_bytes(color="red"))
    first = load_preview(str(file))
    assert load_preview(str(file)) == first
    file.write_bytes(photo_bytes((1500, 1100), "blue"))
    assert load_preview(str(file)) != first


def test_preview_orients_and_strips_metadata(tmp_path):
    from app.utils.private_image_preview import load_preview

    file = tmp_path / "photo.jpg"
    exif = Image.Exif()
    exif[274] = 6
    exif[315] = "private fixture metadata"
    Image.new("RGB", (1600, 1200), "orange").save(file, exif=exif)
    data, media_type = load_preview(str(file))
    preview = Image.open(io.BytesIO(data))
    assert preview.size == (720, 960)
    assert not preview.getexif()
    assert media_type == "image/jpeg"
