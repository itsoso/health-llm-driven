#!/usr/bin/env python3
"""Remove inline answer labels from question crops before they become public assets."""
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw


OCR_MARKER = re.compile(r'答案|SRA|SR1|BRIA|S21', re.IGNORECASE)


def answer_line(path: Path) -> tuple[int, int, int, int]:
    result = subprocess.run(
        ['tesseract', str(path), 'stdout', '-l', 'chi_sim+eng', '--psm', '6', 'tsv'],
        check=True,
        capture_output=True,
        text=True,
    )
    lines: dict[tuple[str, str, str], list[dict[str, str]]] = {}
    for raw in result.stdout.splitlines()[1:]:
        fields = raw.split('\t', 11)
        if len(fields) != 12 or not fields[11].strip():
            continue
        row = dict(zip(('level', 'page_num', 'block_num', 'par_num', 'line_num', 'word_num',
                        'left', 'top', 'width', 'height', 'conf', 'text'), fields))
        lines.setdefault((row['block_num'], row['par_num'], row['line_num']), []).append(row)
    matches = []
    for words in lines.values():
        text = ''.join(word['text'] for word in words)
        left = min(int(word['left']) for word in words)
        if 100 <= left <= 220 and OCR_MARKER.search(text):
            top = min(int(word['top']) for word in words)
            right = max(int(word['left']) + int(word['width']) for word in words)
            bottom = max(int(word['top']) + int(word['height']) for word in words)
            matches.append((left, top, right, bottom))
    if len(matches) != 1:
        raise ValueError(f'{path}: expected one inline answer marker, found {len(matches)}')
    return matches[0]


def redact(path: Path) -> None:
    left, top, right, bottom = answer_line(path)
    with Image.open(path).convert('RGB') as image:
        draw = ImageDraw.Draw(image)
        draw.rectangle((max(0, left - 20), max(0, top - 10), min(image.width, right + 35),
                        min(image.height, bottom + 10)), fill='white')
        image.save(path, 'WEBP', quality=68, method=6)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    paths = sorted(args.directory.glob('q*.webp'))
    if len(paths) != 55:
        raise ValueError(f'Expected 55 question crops, found {len(paths)}')
    for path in paths:
        redact(path)


if __name__ == '__main__':
    main()
