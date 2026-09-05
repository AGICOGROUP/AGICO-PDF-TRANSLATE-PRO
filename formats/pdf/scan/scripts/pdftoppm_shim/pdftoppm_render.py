"""Minimal pdftoppm replacement backed by PyMuPDF.

Supports the exact CLI subset extract_scan.py uses:
    pdftoppm -f N -l M -r DPI -png <source> <prefix>
    pdftoppm -f N -l N -r DPI -png -singlefile <source> <prefix>
Batch mode writes <prefix>-<NN>.png; -singlefile writes <prefix>.png.
"""
import argparse

import fitz


def main() -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("-f", type=int, default=1)
    parser.add_argument("-l", type=int, default=0)
    parser.add_argument("-r", type=float, default=150)
    parser.add_argument("-png", action="store_true")
    parser.add_argument("-singlefile", action="store_true")
    parser.add_argument("source")
    parser.add_argument("prefix")
    args = parser.parse_args()

    document = fitz.open(args.source)
    first = max(1, args.f)
    last = args.l if args.l >= first else document.page_count
    last = min(last, document.page_count)
    zoom = args.r / 72.0
    matrix = fitz.Matrix(zoom, zoom)
    pad = max(2, len(str(document.page_count)))
    for number in range(first, last + 1):
        page = document[number - 1]
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        if args.singlefile:
            target = f"{args.prefix}.png"
        else:
            target = f"{args.prefix}-{number:0{pad}d}.png"
        pixmap.save(target)


if __name__ == "__main__":
    main()
