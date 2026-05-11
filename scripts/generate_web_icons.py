from __future__ import annotations

import argparse
from pathlib import Path

try:
    import cairosvg
except ModuleNotFoundError as exc:  # pragma: no cover - exercised by environment, not tests.
    raise SystemExit(
        "CairoSVG is required to generate web icons. Run `.venv/bin/inv install-deps` first."
    ) from exc


ICON_TARGETS = {
    "Favicon.png": 512,
    "apple-touch-icon.png": 180,
    "pwa-192.png": 192,
    "pwa-512.png": 512,
    "pwa-maskable-512.png": 512,
}


def generate_icons(source: Path, output_dir: Path) -> None:
    if not source.is_file():
        raise SystemExit(f"Source SVG not found: {source}")

    output_dir.mkdir(parents=True, exist_ok=True)
    for filename, size in ICON_TARGETS.items():
        output_path = output_dir / filename
        cairosvg.svg2png(
            url=str(source),
            write_to=str(output_path),
            output_width=size,
            output_height=size,
        )
        print(f"Wrote {output_path} ({size}x{size})")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate web PNG icons from the Planini SVG.")
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("app/web/static/img/planini.svg"),
        help="Source SVG path.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("app/web/static/img"),
        help="Directory that receives generated PNG icons.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    generate_icons(args.source, args.output_dir)


if __name__ == "__main__":
    main()
