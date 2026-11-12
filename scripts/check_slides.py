"""Measure rendered slide PNGs for content overflow and build a contact sheet.

Usage:
    python scripts/check_slides.py output/<slug>/slides

Reads selfcheck.NNN.png files produced by:
    marp --images png -o .../slides/selfcheck
Prints per-page content bottom, flags pages past the safe line, and writes
selfcheck.contact.png next to the pages.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw

SAFE_BOTTOM = 656  # content must end above this y on a 720px-tall slide
DIFF_THRESHOLD = 18
CONTACT_COLS = 4
THUMB_W = 480


def content_bottom(im: Image.Image) -> int | None:
    """Last row containing text/content, ignoring the footer page number.

    Returns None for gradient-background pages (e.g. the cover), where a
    per-row background estimate is not meaningful.
    """
    rgb = im.convert("RGB")
    w, h = rgb.size
    px = rgb.load()

    corners = [(2, 2), (w - 3, 2), (2, h - 3), (w - 3, h - 3)]
    samples = [px[x, y] for x, y in corners]
    spread = max(max(c[i] for c in samples) - min(c[i] for c in samples) for i in range(3))
    if spread > 24:
        return None

    right = w - 140  # page number lives in the bottom-right footer box
    for y in range(h - 1, -1, -1):
        row = [px[x, y] for x in range(0, right, 3)]
        # Background is the modal quantized row colour; text is the minority.
        buckets: dict[tuple[int, int, int], int] = {}
        for c in row:
            key = (c[0] // 16, c[1] // 16, c[2] // 16)
            buckets[key] = buckets.get(key, 0) + 1
        bg_key = max(buckets, key=buckets.get)
        bg = tuple(v * 16 + 8 for v in bg_key)
        ink = 0
        for c in row:
            if (
                abs(c[0] - bg[0]) > DIFF_THRESHOLD
                or abs(c[1] - bg[1]) > DIFF_THRESHOLD
                or abs(c[2] - bg[2]) > DIFF_THRESHOLD
            ):
                ink += 1
        if ink >= 3:
            return y
    return 0


def build_contact(pages: list[Path], out: Path) -> None:
    if not pages:
        return
    cols = CONTACT_COLS
    rows = (len(pages) + cols - 1) // cols
    thumb_h = round(THUMB_W * 9 / 16)
    label_h = 26
    pad = 8
    sheet = Image.new(
        "RGB",
        (cols * (THUMB_W + pad) + pad, rows * (thumb_h + label_h + pad) + pad),
        "#e8eeec",
    )
    draw = ImageDraw.Draw(sheet)
    for i, page in enumerate(pages):
        im = Image.open(page).convert("RGB").resize((THUMB_W, thumb_h))
        row, col = divmod(i, cols)
        x = pad + col * (THUMB_W + pad)
        y = pad + row * (thumb_h + label_h + pad)
        sheet.paste(im, (x, y))
        draw.text((x + 4, y + thumb_h + 4), page.name.replace("selfcheck.", "p."), fill="#17302c")
    sheet.save(out)


def main() -> int:
    global CONTACT_COLS

    ap = argparse.ArgumentParser()
    ap.add_argument("slides_dir", type=Path)
    ap.add_argument("--safe-bottom", type=int, default=SAFE_BOTTOM)
    ap.add_argument("--contact-cols", type=int, default=CONTACT_COLS)
    args = ap.parse_args()

    CONTACT_COLS = args.contact_cols

    pages = sorted(args.slides_dir.glob("selfcheck.*"))
    pages = [p for p in pages if p.suffix not in {".png", ".html", ".md"} or p.name == "selfcheck.contact.png"]
    pages = [p for p in pages if p.name != "selfcheck.contact.png"]
    pages = [p for p in pages if p.name[:10] == "selfcheck." and p.name[10:].isdigit()]
    if not pages:
        print(f"no selfcheck.NNN.png under {args.slides_dir}", file=sys.stderr)
        return 2

    failures = 0
    skipped = 0
    print(f"pages: {len(pages)}")
    for page in pages:
        im = Image.open(page)
        bottom = content_bottom(im)
        if bottom is None:
            skipped += 1
            print(f"{page.name}  {im.width}x{im.height}  gradient background, skipped")
            continue
        flag = "" if bottom <= args.safe_bottom else "  OVERFLOW"
        if flag:
            failures += 1
        print(f"{page.name}  {im.width}x{im.height}  bottom={bottom}{flag}")

    contact = args.slides_dir / "selfcheck.contact.png"
    build_contact(pages, contact)
    print(f"contact: {contact}")
    print(f"OVERALL {'FAIL' if failures else 'PASS'}  ({failures} page(s) past {args.safe_bottom}px)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())