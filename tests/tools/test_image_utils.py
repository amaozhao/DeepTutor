"""Tests for image URL safety helpers."""

from __future__ import annotations

import pytest

from deeptutor.tools.vision.image_utils import ImageError, fetch_image_from_url


@pytest.mark.asyncio
async def test_fetch_image_from_url_rejects_private_host() -> None:
    with pytest.raises(ImageError, match="private|loopback"):
        await fetch_image_from_url("http://127.0.0.1/image.png")
