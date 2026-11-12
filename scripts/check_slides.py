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
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw

SAFE_BOTTOM = 656  # content must end above this y on a 720px-tall slide
DIFF_THRESHOLD = 18
CONTACT_COLS = 4
THUMB_W = 480
SLIDE_W = 1280
IMG_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
WIDTH_RE = re.compile(r"\bw:(\d+)")


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


def deck_source(slides_dir: Path) -> Path | None:
    for name in ("slides.md", "slides.rich.md"):
        candidate = slides_dir / name
        if candidate.exists():
            return candidate
    return None


def iter_deck_images(md: Path):
    """Yield (page, alt, src, declared_width) for every Markdown image."""
    text = md.read_text(encoding="utf-8")
    parts = text.split("\n---\n")
    if parts and parts[0].lstrip().startswith("---"):
        parts = parts[1:]
    for i, part in enumerate(parts, start=1):
        for match in IMG_RE.finditer(part):
            alt = match.group(1).strip()
            src = match.group(2).strip().strip("<>")
            width_match = WIDTH_RE.search(alt)
            yield i, alt, src, int(width_match.group(1)) if width_match else None


def check_images(slides_dir: Path) -> tuple[list[str], list[str], list[str]]:
    """校验课件引用的图片：存在、非外链、未被放大、alt 非空。

    只做确定性判断。图片是否“文字太小/被裁切”仍要人看联系表：
    check_slides 会把每张图的原始尺寸与渲染宽度列出来，方便逐张核对。
    """
    md = deck_source(slides_dir)
    if md is None:
        return [], [], ["  (未找到 slides.md / slides.rich.md，跳过图片检查)"]

    errors: list[str] = []
    warnings: list[str] = []
    inventory: list[str] = []
    for page, alt, src, width in iter_deck_images(md):
        if re.match(r"^(?:https?:)?//", src):
            errors.append(f"p{page} 外链图片（断网会失效）：{src}")
            continue
        if src.startswith("data:"):
            continue
        path = (md.parent / src).resolve()
        if not path.exists():
            errors.append(f"p{page} 图片不存在：{src}")
            continue
        try:
            with Image.open(path) as im:
                natural_w, natural_h = im.size
        except Exception as exc:  # noqa: BLE001 - 任何解码失败都算坏图
            errors.append(f"p{page} 图片无法读取：{src}（{exc}）")
            continue

        label = WIDTH_RE.sub("", alt).strip()
        shown = f"w:{width}" if width else "auto"
        inventory.append(f"  p{page:<3} {path.name:<32} {natural_w}x{natural_h} -> {shown}")
        if not label:
            warnings.append(f"p{page} 图片缺少 alt 文本：{src}")
        if width and width > natural_w * 1.05:
            warnings.append(f"p{page} 图片被放大 {natural_w}->{width}px，会发虚：{path.name}")
    return errors, warnings, inventory


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
    ap.add_argument(
        "--strict-images",
        action="store_true",
        help="图片告警（缺 alt、被放大）也判 FAIL",
    )
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

    img_errors, img_warnings, inventory = check_images(args.slides_dir)
    if inventory:
        print("images:")
        print("\n".join(inventory))
    for warning in img_warnings:
        print(f"WARN image: {warning}")
    for error in img_errors:
        print(f"FAIL image: {error}")

    contact = args.slides_dir / "selfcheck.contact.png"
    build_contact(pages, contact)
    print(f"contact: {contact}")
    failed = failures + len(img_errors)
    if args.strict_images:
        failed += len(img_warnings)
    print(
        f"OVERALL {'FAIL' if failed else 'PASS'}  "
        f"({failures} page(s) past {args.safe_bottom}px, "
        f"{len(img_errors)} image error(s), {len(img_warnings)} warning(s))"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())