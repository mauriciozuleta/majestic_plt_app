"""Builds schedule_b.json from the chapter files of the US Census Schedule B (one .md per chapter, "Structured Schedule B records" tables).

Run by hand when the Census publishes a new edition:  python -m backend.comtrade.data.build_schedule_b "<folder with the 'HS-code chapter N.md' files>"

The output keeps only what the app uses: for every 10-digit statistical line its code, description, the path of headings above it, and the unit(s) of quantity. Chapter 98-99 lines
are kept; headings without a code are dropped.
"""
import json
import re
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent / 'schedule_b.json'
ROW = re.compile(r'^\|\s*(\d{2,4}(?:\.\d{2})?(?:\.\d{4})?)\s*\|(.*)\|\s*$')


def parse_chapter(text: str) -> list[dict]:
    rows = []
    for line in text.splitlines():
        found = ROW.match(line)
        if not found:
            continue
        cells = [cell.strip() for cell in line.strip().strip('|').split('|')]
        if len(cells) < 5:
            continue
        code = cells[0].replace('.', '')
        if not code.isdigit() or len(code) not in (2, 4, 6, 10):
            continue
        rows.append({'code': code, 'description': cells[1].rstrip(':').strip(), 'path': cells[2], 'unit': cells[3] or None, 'unit2': cells[4] or None})
    return rows


def build(folder: Path) -> dict:
    lines = []
    for path in sorted(folder.glob('HS-code chapter *.md'), key=lambda p: int(re.search(r'(\d+)\.md$', p.name).group(1))):
        lines.extend(parse_chapter(path.read_text(encoding='utf-8')))
    leaves = [{'code': row['code'], 'description': row['description'], 'path': row['path'], 'unit': row['unit'], 'unit2': row['unit2']} for row in lines if len(row['code']) == 10]
    headings = {row['code']: row['description'] for row in lines if len(row['code']) in (2, 4, 6)}
    return {'source': 'US Census Bureau, Schedule B - Classification of Exports', 'headings': headings, 'lines': leaves}


if __name__ == '__main__':
    data = build(Path(sys.argv[1]))
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(len(data['lines']), 'ten-digit lines,', len(data['headings']), 'headings ->', OUT)
