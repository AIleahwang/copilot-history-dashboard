"""AI roadmap data loading and HTML rendering."""

import json
from copy import deepcopy
from datetime import date
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent
TEMPLATE_FILE = ROOT / 'ai-roadmap.html'
SEED_FILE = ROOT / 'ai_roadmap_seed.json'
DEFAULT_OVERLAY_FILE = Path.home() / '.follow-builders' / 'ai-roadmap.json'
SCHEMA_VERSION = 1
SOURCE_BACKED_COLLECTIONS = ('signals', 'builders', 'talking_points', 'opportunities', 'watch_next')
ALLOWED_TRACKS = {'foundations', 'learning', 'architecture', 'scale', 'interface', 'ecosystem'}
REQUIRED_ITEM_FIELDS = {
    'signals': ('track', 'title', 'summary', 'why_it_matters', 'source_name'),
    'builders': ('name', 'evidence', 'why_follow'),
    'talking_points': ('claim', 'evidence', 'audience'),
    'opportunities': ('title', 'thesis', 'buyer', 'timing', 'next_step', 'confidence'),
    'watch_next': ('question', 'why'),
}
REQUIRED_CONTEXT_FIELDS = (
    'id',
    'period',
    'title',
    'summary',
    'everyday_example',
    'implication',
)
REQUIRED_PERSON_FIELDS = ('name', 'period', 'role', 'impact', 'credit')
REQUIRED_ORGANIZATION_FIELDS = ('name', 'period', 'role')


class RoadmapDataError(ValueError):
    """Raised when roadmap data is missing or malformed."""


def _read_object(path, label):
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError as exc:
        raise RoadmapDataError(f'{label} not found: {path}') from exc
    except json.JSONDecodeError as exc:
        raise RoadmapDataError(f'{label} is invalid JSON at line {exc.lineno}: {path}') from exc
    if not isinstance(data, dict):
        raise RoadmapDataError(f'{label} must be a JSON object: {path}')
    return data


def _is_source_url(value):
    if not isinstance(value, str):
        return False
    parsed = urlparse(value.strip())
    return parsed.scheme in ('http', 'https') and bool(parsed.netloc)


def _require_non_empty_strings(item, fields, label):
    for field in fields:
        if not isinstance(item.get(field), str) or not item[field].strip():
            raise RoadmapDataError(f'{label}.{field} must be a non-empty string')


def validate_seed(seed):
    chapters = seed.get('context_chapters')
    if not isinstance(chapters, list) or not chapters:
        raise RoadmapDataError('AI roadmap seed "context_chapters" must be a non-empty array')

    chapter_ids = set()
    for index, chapter in enumerate(chapters):
        label = f'context_chapters[{index}]'
        if not isinstance(chapter, dict):
            raise RoadmapDataError(f'{label} must be an object')
        _require_non_empty_strings(chapter, REQUIRED_CONTEXT_FIELDS, label)
        if chapter['id'] in chapter_ids:
            raise RoadmapDataError(f'{label}.id must be unique')
        chapter_ids.add(chapter['id'])

        start_year = chapter.get('start_year')
        end_year = chapter.get('end_year')
        if (
            isinstance(start_year, bool)
            or isinstance(end_year, bool)
            or not isinstance(start_year, int)
            or not isinstance(end_year, int)
            or start_year > end_year
        ):
            raise RoadmapDataError(f'{label} requires integer start_year <= end_year')

        landmarks = chapter.get('landmarks')
        if (
            not isinstance(landmarks, list)
            or not landmarks
            or any(not isinstance(item, str) or not item.strip() for item in landmarks)
        ):
            raise RoadmapDataError(f'{label}.landmarks must be a non-empty array of strings')
        if not _is_source_url(chapter.get('source_url')):
            raise RoadmapDataError(f'{label} requires an http(s) source_url')

    people = seed.get('history_people')
    if not isinstance(people, list) or not people:
        raise RoadmapDataError('AI roadmap seed "history_people" must be a non-empty array')
    for index, person in enumerate(people):
        label = f'history_people[{index}]'
        if not isinstance(person, dict):
            raise RoadmapDataError(f'{label} must be an object')
        _require_non_empty_strings(person, REQUIRED_PERSON_FIELDS, label)
        for field in ('image_url', 'profile_url', 'credit_url'):
            if not _is_source_url(person.get(field)):
                raise RoadmapDataError(f'{label} requires an http(s) {field}')

    organizations = seed.get('history_organizations')
    if not isinstance(organizations, list) or not organizations:
        raise RoadmapDataError('AI roadmap seed "history_organizations" must be a non-empty array')
    for index, organization in enumerate(organizations):
        label = f'history_organizations[{index}]'
        if not isinstance(organization, dict):
            raise RoadmapDataError(f'{label} must be an object')
        _require_non_empty_strings(organization, REQUIRED_ORGANIZATION_FIELDS, label)
        for field in ('logo_url', 'profile_url'):
            if not _is_source_url(organization.get(field)):
                raise RoadmapDataError(f'{label} requires an http(s) {field}')
    return seed


def validate_weekly_update(update):
    if not isinstance(update, dict):
        raise RoadmapDataError('weekly update must be a JSON object')

    week = update.get('week')
    try:
        date.fromisoformat(week)
    except (TypeError, ValueError) as exc:
        raise RoadmapDataError('weekly update "week" must use YYYY-MM-DD') from exc

    for field in ('headline', 'executive_summary'):
        if not isinstance(update.get(field), str) or not update[field].strip():
            raise RoadmapDataError(f'weekly update "{field}" must be a non-empty string')

    for collection in SOURCE_BACKED_COLLECTIONS:
        items = update.get(collection, [])
        if not isinstance(items, list):
            raise RoadmapDataError(f'weekly update "{collection}" must be an array')
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise RoadmapDataError(f'{collection}[{index}] must be an object')
            _require_non_empty_strings(
                item,
                REQUIRED_ITEM_FIELDS[collection],
                f'{collection}[{index}]'
            )
            if not _is_source_url(item.get('source_url')):
                raise RoadmapDataError(f'{collection}[{index}] requires an http(s) source_url')

    for index, signal in enumerate(update.get('signals', [])):
        if signal['track'] not in ALLOWED_TRACKS:
            raise RoadmapDataError(f'signals[{index}].track is not a supported roadmap track')

    for index, builder in enumerate(update.get('builders', [])):
        score = builder.get('score')
        breakdown = builder.get('breakdown')
        if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 100:
            raise RoadmapDataError(f'builders[{index}].score must be an integer from 0 to 100')
        if score < 70:
            raise RoadmapDataError(f'builders[{index}] does not meet the 70-point qualification gate')
        if not isinstance(breakdown, dict):
            raise RoadmapDataError(f'builders[{index}].breakdown must be an object')
        required = {'building': 40, 'originality': 25, 'relevance': 25, 'source_quality': 10}
        total = 0
        for key, maximum in required.items():
            value = breakdown.get(key)
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
                raise RoadmapDataError(
                    f'builders[{index}].breakdown.{key} must be an integer from 0 to {maximum}'
                )
            total += value
        if total != score:
            raise RoadmapDataError(f'builders[{index}] score must equal its rubric breakdown')
        if breakdown['building'] < 24 or breakdown['originality'] < 15 or breakdown['relevance'] < 15:
            raise RoadmapDataError(f'builders[{index}] does not meet the rubric sub-score gates')

    for index, opportunity in enumerate(update.get('opportunities', [])):
        if opportunity['confidence'].lower() not in {'high', 'medium', 'low'}:
            raise RoadmapDataError(
                f'opportunities[{index}].confidence must be high, medium, or low'
            )

    return update


def load_overlay(path=DEFAULT_OVERLAY_FILE):
    path = Path(path)
    if not path.exists():
        return {'schema_version': SCHEMA_VERSION, 'weekly_updates': []}
    overlay = _read_object(path, 'AI roadmap overlay')
    if overlay.get('schema_version') != SCHEMA_VERSION:
        raise RoadmapDataError(
            f'AI roadmap overlay schema_version must be {SCHEMA_VERSION}: {path}'
        )
    updates = overlay.get('weekly_updates', [])
    if not isinstance(updates, list):
        raise RoadmapDataError(f'AI roadmap overlay "weekly_updates" must be an array: {path}')
    for update in updates:
        validate_weekly_update(update)
    overlay['weekly_updates'] = sorted(updates, key=lambda item: item['week'], reverse=True)
    return overlay


def load_roadmap_data(overlay_path=DEFAULT_OVERLAY_FILE):
    seed = _read_object(SEED_FILE, 'AI roadmap seed')
    if seed.get('schema_version') != SCHEMA_VERSION:
        raise RoadmapDataError(f'AI roadmap seed schema_version must be {SCHEMA_VERSION}')
    validate_seed(seed)

    overlay_path = Path(overlay_path)
    overlay = load_overlay(overlay_path)
    data = deepcopy(seed)
    data['weekly_updates'] = overlay['weekly_updates']
    data['runtime'] = {
        'mode': 'live' if overlay['weekly_updates'] else 'baseline',
        'updated_at': overlay.get('updated_at') or seed.get('meta', {}).get('baseline_as_of'),
    }
    return data


def render_ai_roadmap(overlay_path=DEFAULT_OVERLAY_FILE):
    template = TEMPLATE_FILE.read_text(encoding='utf-8')
    marker = '__AI_ROADMAP_DATA__'
    if marker not in template:
        raise RoadmapDataError(f'AI roadmap template is missing {marker}')
    payload = json.dumps(load_roadmap_data(overlay_path), ensure_ascii=False, separators=(',', ':'))
    payload = payload.replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e')
    return template.replace(marker, payload)


def roadmap_json(overlay_path=DEFAULT_OVERLAY_FILE):
    return json.dumps(load_roadmap_data(overlay_path), ensure_ascii=False)
