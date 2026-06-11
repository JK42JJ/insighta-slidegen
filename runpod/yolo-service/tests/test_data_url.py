"""PR-H2: data-url support on the YOLO serving wrapper.

The CV service ships frames/crops as base64 data URLs (same call shape as the
Qwen path); httpx cannot fetch the data: scheme, so app._load_image_bytes
decodes it inline. Also covers the url-masking of /detect error details
(presigned GET urls carry a signature — they must never echo back).
"""

import base64
import io

import pytest
from PIL import Image

from app import _load_image_bytes

# 1x1 red PNG, generated in-memory — no fixtures, no network.
def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (1, 1), (255, 0, 0)).save(buf, format="PNG")
    return buf.getvalue()


def _data_url(payload: bytes, mime: str = "image/png") -> str:
    return f"data:{mime};base64,{base64.b64encode(payload).decode()}"


def test_data_url_roundtrip():
    payload = _png_bytes()
    assert _load_image_bytes(_data_url(payload)) == payload


def test_data_url_decodes_to_an_openable_image():
    image = Image.open(io.BytesIO(_load_image_bytes(_data_url(_png_bytes()))))
    assert image.size == (1, 1)


def test_data_url_without_base64_marker_is_rejected():
    with pytest.raises(ValueError, match="base64"):
        _load_image_bytes("data:image/png,rawpayload")


def test_data_url_without_payload_is_rejected():
    with pytest.raises(ValueError):
        _load_image_bytes("data:image/png;base64,")


def test_detect_masks_urls_out_of_fetch_error_details(monkeypatch):
    """A failing presigned url (signature inside!) must not echo back into
    the 422 detail — the mask replaces every url with <url>."""
    from fastapi.testclient import TestClient

    import app as app_module

    presigned = "https://bucket.s3.example/frames/f.jpg?X-Amz-Signature=SECRETSIG"

    def _raise_with_url(*_args, **_kwargs):
        raise RuntimeError(f"fetch failed for {presigned}")

    monkeypatch.setenv("YOLO_KEY", "test-key")
    monkeypatch.setattr(app_module.httpx, "get", _raise_with_url)
    client = TestClient(app_module.app)
    response = client.post(
        "/detect",
        json={"image_url": presigned},
        headers={"Authorization": "Bearer test-key"},
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "X-Amz-Signature" not in detail
    assert "SECRETSIG" not in detail
    assert "<url>" in detail
