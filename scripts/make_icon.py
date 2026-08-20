"""Gera o ícone do microfone (assets/icon.ico e .png) usado no .exe e na bandeja."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PIL import Image, ImageDraw

ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
os.makedirs(ASSETS, exist_ok=True)

ACCENT = (10, 132, 255, 255)


def draw(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 64.0
    d.ellipse((17 * s, 6 * s, 47 * s, 36 * s), fill=ACCENT)
    d.rounded_rectangle((14 * s, 44 * s, 50 * s, 49 * s), radius=2 * s, fill=ACCENT)
    d.rounded_rectangle((29 * s, 34 * s, 35 * s, 52 * s), radius=3 * s, fill=ACCENT)
    return img


if __name__ == "__main__":
    draw(512).save(os.path.join(ASSETS, "icon.png"))
    draw(256).save(os.path.join(ASSETS, "icon.ico"), sizes=[(256, 256), (64, 64), (48, 48), (32, 32), (16, 16)])
    print("ícones em", ASSETS)
