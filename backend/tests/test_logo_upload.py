"""اختبارات رفع الشعار: صور صالحة، امتداد مزيف، حجم زائد، ملف تالف."""

import io

import pytest
from PIL import Image

LOGO_URL = "/api/v1/school/settings/logo/"


def _image_bytes(fmt: str = "PNG", size=(64, 64)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color=(30, 90, 200)).save(buffer, format=fmt)
    return buffer.getvalue()


def _upload(client, filename: str, content: bytes, content_type: str = "image/png"):
    from django.core.files.uploadedfile import SimpleUploadedFile

    file = SimpleUploadedFile(filename, content, content_type=content_type)
    return client.post(LOGO_URL, {"logo": file})


@pytest.mark.django_db
def test_valid_png_accepted(role_client):
    client, _, _ = role_client(["SCHOOL_MANAGER"])
    response = _upload(client, "logo.png", _image_bytes("PNG"))
    assert response.status_code == 200
    assert response.json()["logo_url"].startswith(f"{LOGO_URL}?v=")

    delivered = client.get(response.json()["logo_url"])
    assert delivered.status_code == 200
    assert delivered["Content-Type"] == "image/png"
    assert "no-store" in delivered["Cache-Control"]
    assert b"".join(delivered.streaming_content).startswith(b"\x89PNG\r\n\x1a\n")


@pytest.mark.django_db
def test_valid_jpg_accepted(role_client):
    client, _, _ = role_client(["SCHOOL_MANAGER"])
    response = _upload(client, "logo.jpg", _image_bytes("JPEG"), content_type="image/jpeg")
    assert response.status_code == 200


@pytest.mark.django_db
def test_fake_extension_text_file_rejected(role_client):
    client, _, _ = role_client(["SCHOOL_MANAGER"])
    response = _upload(client, "logo.png", b"this is not an image at all")
    assert response.status_code == 400


@pytest.mark.django_db
def test_disallowed_real_format_rejected(role_client):
    """محتوى BMP باسم png — فحص المحتوى الفعلي عبر Pillow يرفضه."""
    client, _, _ = role_client(["SCHOOL_MANAGER"])
    response = _upload(client, "logo.png", _image_bytes("BMP"))
    assert response.status_code == 400


@pytest.mark.django_db
def test_oversized_file_rejected(role_client):
    client, _, _ = role_client(["SCHOOL_MANAGER"])
    big = _image_bytes("PNG") + b"\x00" * (2 * 1024 * 1024 + 1)
    response = _upload(client, "logo.png", big)
    assert response.status_code == 400


@pytest.mark.django_db
def test_bad_extension_rejected(role_client):
    client, _, _ = role_client(["SCHOOL_MANAGER"])
    response = _upload(client, "logo.gif", _image_bytes("PNG"))
    assert response.status_code == 400


@pytest.mark.django_db
def test_non_manager_cannot_upload(role_client):
    client, _, _ = role_client(["VICE_PRINCIPAL"])
    response = _upload(client, "logo.png", _image_bytes("PNG"))
    assert response.status_code == 403


@pytest.mark.django_db
def test_remove_logo(role_client):
    client, _, _ = role_client(["SCHOOL_MANAGER"])
    _upload(client, "logo.png", _image_bytes("PNG"))
    response = client.delete(LOGO_URL)
    assert response.status_code == 200
    assert response.json()["logo_url"] is None


@pytest.mark.django_db
def test_missing_logo_delivery_returns_404(role_client):
    client, _, _ = role_client(["SCHOOL_MANAGER"])
    response = client.get(LOGO_URL)
    assert response.status_code == 404
