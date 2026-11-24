"""Draw Bao's app icon (the panda on a rounded tile) and build ``packaging/Bao.icns``.

Usage:
    python tools/gen_icon.py              # writes packaging/Bao.icns (needs macOS iconutil)
    python tools/gen_icon.py --png x.png  # also writes the 1024 px PNG for review
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gen_panda import SIZE, idle  # noqa: E402  (sets QT_QPA_PLATFORM=offscreen)
from gen_panda import draw_panda as draw  # noqa: E402
from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "packaging" / "Bao.icns"
ICONSET_SIZES = [16, 32, 128, 256, 512]  # each also @2x


def render_icon(px: int = 1024) -> QImage:
    img = QImage(px, px, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    # macOS Big Sur-style tile: ~80% of the canvas, continuous-ish corners.
    inset = px * 0.1
    tile = QRectF(inset, inset, px - 2 * inset, px - 2 * inset)
    grad = QLinearGradient(tile.topLeft(), tile.bottomLeft())
    grad.setColorAt(0, QColor("#f6e3c9"))
    grad.setColorAt(1, QColor("#e9a27f"))
    p.setPen(Qt.NoPen)
    p.setBrush(grad)
    radius = tile.width() * 0.225
    p.drawRoundedRect(tile, radius, radius)
    clip = QPainterPath()
    clip.addRoundedRect(tile, radius, radius)
    p.setClipPath(clip)
    # Panda, scaled from its 160 px design grid to fill the tile.
    scale = tile.width() / SIZE * 0.95
    p.translate(tile.center().x() - SIZE * scale / 2, tile.top() + tile.height() * 0.02)
    p.scale(scale, scale)
    draw(p, idle(0.0, 0), 0.0)
    p.end()
    return img


def build_icns(out: Path, png: Path | None = None) -> None:
    big = render_icon(1024)
    if png:
        big.save(str(png))
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "Bao.iconset"
        iconset.mkdir()
        for s in ICONSET_SIZES:
            for mult, suffix in ((1, ""), (2, "@2x")):
                img = big.scaled(s * mult, s * mult, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                img.save(str(iconset / f"icon_{s}x{s}{suffix}.png"))
        if not shutil.which("iconutil"):
            raise SystemExit("iconutil not found (it ships with macOS)")
        out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(out)], check=True)
    print(f"wrote {out}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--png", type=Path, help="also save the 1024 px icon as a PNG")
    args = ap.parse_args()
    _app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    build_icns(args.out, args.png)


if __name__ == "__main__":
    main()
