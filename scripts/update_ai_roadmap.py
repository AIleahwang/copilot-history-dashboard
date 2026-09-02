#!/usr/bin/env python
"""Validate and persist one source-backed weekly AI roadmap update."""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai_roadmap_view import (  # noqa: E402
    DEFAULT_OVERLAY_FILE,
    SCHEMA_VERSION,
    RoadmapDataError,
    load_overlay,
    validate_weekly_update,
)


def _read_input(path):
    if path == '-':
        raw = sys.stdin.read()
        label = 'stdin'
    else:
        input_path = Path(path)
        raw = input_path.read_text(encoding='utf-8')
        label = str(input_path)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RoadmapDataError(f'update input is invalid JSON at line {exc.lineno}: {label}') from exc
    if isinstance(data, dict) and isinstance(data.get('update'), dict):
        data = data['update']
    return validate_weekly_update(data)


def persist_update(update, output_path=DEFAULT_OVERLAY_FILE):
    update = validate_weekly_update(update)
    output_path = Path(output_path)
    overlay = load_overlay(output_path)
    updates = [item for item in overlay['weekly_updates'] if item['week'] != update['week']]
    updates.append(update)
    updates.sort(key=lambda item: item['week'], reverse=True)

    payload = {
        'schema_version': SCHEMA_VERSION,
        'updated_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'weekly_updates': updates[:104],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + '.tmp')
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(output_path)
    return output_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, help='Update JSON file, or - for stdin')
    parser.add_argument('--output', default=str(DEFAULT_OVERLAY_FILE), help='Overlay JSON destination')
    parser.add_argument('--check', action='store_true', help='Validate without writing')
    args = parser.parse_args()

    try:
        update = _read_input(args.input)
        if args.check:
            print(f'valid weekly update: {update["week"]}')
            return 0
        destination = persist_update(update, args.output)
        print(f'updated AI roadmap: {destination}')
        return 0
    except (OSError, RoadmapDataError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
