"""Textures for the renders: 16x2 LCD screens (HD44780-style 5x8 dot matrix) and the breadboard.

    python cad/render/textures.py      ->  cad/render/tex/*.png
"""

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

TEX = Path(__file__).with_name("tex")
FONT = "C:/Windows/Fonts/consolab.ttf"

# Text shown on the LCD in each shot (16 characters per line, like the real 1602)
SCREENS = {
    "hero": ("SuppBuddy  READY", "Insert sample..."),
    "exploded": ("VIT C     1000mg", "MATCH 96%   PASS"),
    "cutaway": ("SCANNING  IR 4/4", "█" * 9 + "    62%"),
}

# GDM1602K geometry (mm): viewing area, character pitch and size, dot grid
VIEW_W, VIEW_H = 64.5, 16.4
PITCH_X, PITCH_Y = 3.55, 5.95
CHAR_W, CHAR_H = 2.95, 5.55
PX = 40  # texture pixels per mm


def glyph(ch, font):
    """Rasterise one character to a 5x8 dot pattern (row 8 left blank, as on the HD44780)."""
    if ch == " ":
        return np.zeros((8, 5), bool)
    if ch == "█":  # HD44780 full block
        return np.ones((8, 5), bool)
    im = Image.new("L", (250, 400), 0)
    d = ImageDraw.Draw(im)
    d.text((125, 350), ch, font=font, fill=255, anchor="ms")
    # scale the cap-height region to 7 rows and the advance width to 5 columns
    cap_top = 350 + int(font.getbbox("H", anchor="ms")[1])
    half = int(font.getlength("M") * 0.47)
    crop = im.crop((125 - half, cap_top, 125 + half, 350))
    small = np.asarray(crop.resize((5, 7), Image.BOX), float) / 255
    out = np.zeros((8, 5), bool)
    out[:7] = small > 0.30
    if ch in "gjpqy,":  # descenders: drop into row 8
        out[7] = np.asarray(im.crop((125 - half, 350, 125 + half, 350 + (350 - cap_top) // 7)).resize((5, 1), Image.BOX))[0] > 60
    return out


def lcd(lines, path):
    font = ImageFont.truetype(FONT, 300)
    w, h = int(VIEW_W * PX), int(VIEW_H * PX)
    # backlight: blue, slightly brighter in the middle
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.hypot((xx - w / 2) / (w / 2), (yy - h / 2) / (h / 2))
    base = np.array([28, 78, 245], float)
    img = base[None, None, :] * (1.0 - 0.18 * np.clip(r, 0, 1.4)[..., None])
    im = Image.fromarray(img.clip(0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    x0 = (VIEW_W - (16 * PITCH_X - (PITCH_X - CHAR_W))) / 2
    y0 = (VIEW_H - (PITCH_Y + CHAR_H)) / 2
    dot_w, dot_h = CHAR_W / 5, CHAR_H / 8
    for row, text in enumerate(lines):
        for col, ch in enumerate(text.ljust(16)[:16]):
            g = glyph(ch, font)
            cx = x0 + col * PITCH_X
            cy = y0 + row * PITCH_Y
            for j in range(8):
                for i in range(5):
                    on = g[j, i]
                    fill = (235, 243, 255) if on else (40, 92, 250)
                    xa = (cx + i * dot_w + 0.04) * PX
                    ya = (cy + j * dot_h + 0.04) * PX
                    d.rectangle([xa, ya, xa + (dot_w - 0.08) * PX, ya + (dot_h - 0.08) * PX], fill=fill)
    im = im.filter(ImageFilter.GaussianBlur(0.6))
    im.save(path)


def breadboard(path):
    """Half-size breadboard top, 84 x 55 mm: 30 columns of 2x5 tie points plus 2 power rails per side."""
    s = 20  # px/mm
    w, h = 84 * s, 55 * s
    im = Image.new("RGB", (w, h), (238, 236, 229))
    d = ImageDraw.Draw(im)
    p = 2.54
    hole = 0.95

    def sq(x, y, c=(55, 55, 58)):
        d.rounded_rectangle([(x - hole / 2) * s, (y - hole / 2) * s, (x + hole / 2) * s, (y + hole / 2) * s],
                            radius=0.18 * s, fill=c)

    x_first = (84 - 29 * p) / 2
    cy = 55 / 2
    # terminal strips: rows a-e above the channel, f-j below
    for col in range(30):
        x = x_first + col * p
        for k in range(5):
            sq(x, cy - p * 1.5 - k * p)
            sq(x, cy + p * 1.5 + k * p)
    # centre channel
    d.rectangle([3 * s, (cy - 0.9) * s, 81 * s, (cy + 0.9) * s], fill=(214, 211, 202))
    # power rails: 25 holes in groups of 5, two rows each side
    for side in (-1, 1):
        ys = [cy + side * (p * 6.5 + 2.2), cy + side * (p * 7.5 + 2.2)]
        for g in range(5):
            for k in range(5):
                x = x_first + g * 6 * p + k * p
                for y in ys:
                    sq(x, y)
        line_y = [ys[0] - side * 1.6, ys[1] + side * 1.6]
        for ly, c in zip(line_y, [(40, 80, 200), (210, 40, 40)] if side < 0 else [(210, 40, 40), (40, 80, 200)]):
            d.line([(4 * s, ly * s), (80 * s, ly * s)], fill=c, width=int(0.35 * s))
    im.save(path)


def main():
    TEX.mkdir(exist_ok=True)
    for name, lines in SCREENS.items():
        lcd(lines, TEX / f"lcd_{name}.png")
    breadboard(TEX / "breadboard.png")
    print("wrote", sorted(p.name for p in TEX.glob("*.png")))


if __name__ == "__main__":
    main()
