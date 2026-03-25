"""
Image generation — DALL-E 3 (OpenAI) med HuggingFace FLUX fallback.

Primær:  HuggingFace FLUX.1-schnell (gratis, fungerer alltid)
Fallback: DALL-E 3 hvis OpenAI billing er ok
"""
import logging
import os
import uuid
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("/opt/nexus/outputs/images")


def generate_image(
    prompt: str,
    size: str = "1024x1024",
    quality: str = "standard",
    output_path: str | None = None,
) -> str:
    """
    Generate an image. Tries HuggingFace FLUX first (free), falls back to DALL-E 3.

    Args:
        prompt: Image description
        size: '1024x1024', '1024x1792', '1792x1024'
        quality: 'standard' or 'hd'
        output_path: Where to save the image

    Returns:
        Path to saved image
    """
    try:
        return generate_flux(prompt, output_path=output_path)
    except Exception as e:
        logger.warning(f"FLUX failed ({e}), trying DALL-E 3")
        try:
            return generate_dalle(prompt, size=size, quality=quality, output_path=output_path)
        except Exception as e2:
            logger.error(f"All image gen failed. FLUX: {e} | DALLE: {e2}")
            raise RuntimeError(f"Image generation unavailable: {e2}") from e2


from tools.circuit_breaker import breaker, smart_retry

@breaker(huggingface, fail_max=3, reset_timeout=120)
def generate_flux(
    prompt: str,
    model: str = "black-forest-labs/FLUX.1-schnell",
    output_path: str | None = None,
) -> str:
    """
    Generate image via HuggingFace FLUX (free tier).

    Args:
        prompt: Image description
        model: HuggingFace model ID
        output_path: Where to save

    Returns:
        Path to saved image
    """
    key = os.getenv("HUGGINGFACE_API_KEY", "")
    if not key:
        raise ValueError("HUGGINGFACE_API_KEY not set")

    resp = httpx.post(
        f"https://router.huggingface.co/hf-inference/models/{model}",
        headers={"Authorization": f"Bearer {key}"},
        json={"inputs": prompt},
        timeout=60.0,
    )
    if not resp.is_success:
        raise RuntimeError(f"HuggingFace {resp.status_code}: {resp.text[:200]}")

    return _save_image(resp.content, output_path)


def generate_dalle(
    prompt: str,
    size: str = "1024x1024",
    quality: str = "standard",
    output_path: str | None = None,
) -> str:
    """
    Generate image via DALL-E 3. Requires active OpenAI billing.

    Returns:
        Path to saved image
    """
    key = os.getenv("OPENAI_API_KEY", "")
    if not key:
        raise ValueError("OPENAI_API_KEY not set")

    resp = httpx.post(
        "https://api.openai.com/v1/images/generations",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": "dall-e-3", "prompt": prompt, "n": 1, "size": size, "quality": quality},
        timeout=60.0,
    )
    if not resp.is_success:
        body = resp.json().get("error", {})
        raise RuntimeError(f"DALL-E {resp.status_code}: {body.get('message', resp.text[:200])}")

    image_url = resp.json()["data"][0]["url"]
    img_data = httpx.get(image_url, timeout=30.0).content
    return _save_image(img_data, output_path)


def _save_image(data: bytes, output_path: str | None) -> str:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if not output_path:
        output_path = str(OUTPUT_DIR / f"img_{uuid.uuid4().hex[:8]}.jpg")
    Path(output_path).write_bytes(data)
    logger.info(f"Image saved: {output_path} ({len(data)//1024}KB)")
    return output_path
