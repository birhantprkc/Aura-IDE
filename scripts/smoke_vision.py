"""Smoke 5: image input verification on deepseek-v4-pro and deepseek-v4-flash.

Generates a small PNG containing a recognizable shape and a number, sends it via
the OpenAI content-array format, and prints the model's response. Documents the
result so Phase 1 can decide whether to enable image input in the GUI.
"""
from __future__ import annotations

import base64
import io
import os
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from PIL import Image, ImageDraw, ImageFont
from openai import OpenAI

from aura.config import DEEPSEEK_BASE_URL, ENV_API_KEY


def make_test_png() -> bytes:
    """A 256x256 PNG: white background, big red circle, big number '7' inside."""
    img = Image.new("RGB", (256, 256), "white")
    draw = ImageDraw.Draw(img)
    draw.ellipse((40, 40, 216, 216), fill="red", outline="black", width=4)
    try:
        font = ImageFont.truetype("arial.ttf", 140)
    except OSError:
        font = ImageFont.load_default()
    # Center the "7" approximately.
    bbox = draw.textbbox((0, 0), "7", font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((256 - w) / 2 - bbox[0], (256 - h) / 2 - bbox[1]), "7", fill="white", font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def call_with_image(client: OpenAI, model: str, b64: str) -> tuple[bool, str]:
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "Look at this image. Describe what shape and what single digit you see. "
                        "Reply in one sentence."
                    ),
                },
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b64}"},
                },
            ],
        }
    ]
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            stream=False,
        )
        return True, (resp.choices[0].message.content or "").strip()
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def main() -> int:
    api_key = os.environ.get(ENV_API_KEY)
    if not api_key:
        print(f"FAIL: {ENV_API_KEY} not set")
        return 1

    png = make_test_png()
    # Persist to tmp for visual confirmation if user wants to look.
    tmp_path = Path(tempfile.gettempdir()) / "aura_vision_test.png"
    tmp_path.write_bytes(png)
    print(f"test image: {tmp_path} ({len(png)} bytes)")
    b64 = base64.b64encode(png).decode("ascii")

    client = OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)

    print("\n--- deepseek-v4-pro ---")
    ok_pro, out_pro = call_with_image(client, "deepseek-v4-pro", b64)
    print(("RESPONSE: " if ok_pro else "ERROR: ") + out_pro)

    print("\n--- deepseek-v4-flash ---")
    ok_flash, out_flash = call_with_image(client, "deepseek-v4-flash", b64)
    print(("RESPONSE: " if ok_flash else "ERROR: ") + out_flash)

    print("\n--- summary ---")
    pro_saw_circle_and_7 = ok_pro and ("circle" in out_pro.lower() or "round" in out_pro.lower()) and "7" in out_pro
    flash_saw_circle_and_7 = ok_flash and ("circle" in out_flash.lower() or "round" in out_flash.lower()) and "7" in out_flash
    print(f"pro:   ok={ok_pro}, recognized={pro_saw_circle_and_7}")
    print(f"flash: ok={ok_flash}, recognized={flash_saw_circle_and_7}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
