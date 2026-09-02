import json
import shutil
import subprocess
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from ai_roadmap_view import RoadmapDataError, load_roadmap_data, render_ai_roadmap, validate_seed
from scripts.update_ai_roadmap import persist_update


def valid_update(week='2026-08-07'):
    return {
        'week': week,
        'headline': 'Agent reliability becomes the product boundary',
        'executive_summary': 'Builders shipped concrete agent infrastructure with traceable evidence.',
        'signals': [
            {
                'track': 'ecosystem',
                'title': 'A source-backed launch',
                'summary': 'The builder shipped a concrete product update.',
                'why_it_matters': 'It changes how teams operate long-running agents.',
                'source_name': 'Builder on X',
                'published_at': week,
                'source_url': 'https://twitter.com/example/status/123'
            }
        ],
        'builders': [
            {
                'name': 'Example Builder',
                'role': 'Founder',
                'handle': 'builder',
                'score': 80,
                'breakdown': {
                    'building': 32,
                    'originality': 18,
                    'relevance': 20,
                    'source_quality': 10
                },
                'evidence': 'Shipped a working product and explained the architecture.',
                'why_follow': 'Provides actionable implementation evidence.',
                'source_url': 'https://youtu.be/example-video'
            }
        ],
        'talking_points': [],
        'opportunities': [],
        'watch_next': []
    }


class RoadmapTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.overlay = Path(self.tempdir.name) / 'ai-roadmap.json'

    def tearDown(self):
        self.tempdir.cleanup()

    def test_seed_loads_without_personal_overlay(self):
        data = load_roadmap_data(self.overlay)
        self.assertEqual(data['runtime']['mode'], 'baseline')
        self.assertGreater(len(data['eras']), 10)
        self.assertEqual(len(data['context_chapters']), 6)
        self.assertEqual(len(data['history_people']), 6)
        self.assertEqual(len(data['history_organizations']), 8)
        self.assertEqual(data['weekly_updates'], [])

    def test_update_is_persisted_and_rendered(self):
        persist_update(valid_update(), self.overlay)
        data = load_roadmap_data(self.overlay)
        page = render_ai_roadmap(self.overlay)

        self.assertEqual(data['runtime']['mode'], 'live')
        self.assertEqual(data['weekly_updates'][0]['week'], '2026-08-07')
        self.assertNotIn('__AI_ROADMAP_DATA__', page)
        self.assertIn('Agent reliability becomes the product boundary', page)
        self.assertNotIn('Mission Milestones', page)
        self.assertNotIn('achievementToast', page)
        self.assertNotIn('Scout progression', page)
        self.assertNotIn(' XP', page)
        self.assertIn('data-design-system="midnight-atlas-paper"', page)
        self.assertIn('data-view="map"', page)
        self.assertIn('id="atlasWorld"', page)
        self.assertIn('id="atlasCityNetwork"', page)
        self.assertIn('id="historyAtlas"', page)
        self.assertIn('id="historyContextChapters"', page)
        self.assertIn('id="historyPeople"', page)
        self.assertIn('id="historyOrganizations"', page)
        self.assertIn('data-history-media', page)
        self.assertIn('图像来源 ·', page)
        self.assertIn('id="historyStoryline"', page)
        self.assertIn('id="historyLanes"', page)
        self.assertIn('AI Evolution', page)
        self.assertIn('view", "history"', page)
        self.assertIn('data-navigation="same-tab"', page)
        self.assertNotIn('target="_blank"', page)
        self.assertIn('const historyScale = [', page)
        self.assertIn('data-history-node=', page)
        self.assertIn('在 X 查看原帖 ↗', page)
        self.assertIn('观看原始视频 ↗', page)
        self.assertIn('查看原始来源 ↗', page)
        self.assertIn('parsed.hostname = "x.com"', page)
        self.assertIn('Midnight Atlas world', page)
        self.assertIn('atlas-region-panel', page)
        self.assertNotIn('ME / 01 · SWISS GRID · PIXEL SYSTEM', page)
        self.assertNotIn('Hard gate', page)
        self.assertNotIn('HARD GATE', page)
        self.assertNotIn('PTS', page)
        self.assertNotIn('CITY 01', page)
        self.assertNotIn('<div class="hero-stats">', page)

    def test_same_week_is_replaced_and_archive_is_sorted(self):
        persist_update(valid_update('2026-07-31'), self.overlay)
        replacement = valid_update('2026-07-31')
        replacement['headline'] = 'Replacement'
        persist_update(replacement, self.overlay)
        persist_update(valid_update('2026-08-07'), self.overlay)

        raw = json.loads(self.overlay.read_text(encoding='utf-8'))
        self.assertEqual([item['week'] for item in raw['weekly_updates']], ['2026-08-07', '2026-07-31'])
        self.assertEqual(raw['weekly_updates'][1]['headline'], 'Replacement')

    def test_client_source_descriptor_routes_original_platforms(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('Node.js is required to execute the browser URL helper')

        template_path = Path(__file__).resolve().parents[1] / 'ai-roadmap.html'
        template = template_path.read_text(encoding='utf-8')
        helper_start = template.index('      const safeUrl =')
        helper_end = template.index('      const sourceAnchor =', helper_start)
        helper = template[helper_start:helper_end]
        script = helper + '''
          console.log(JSON.stringify({
            x: sourceDescriptor("https://twitter.com/example/status/123"),
            youtube: sourceDescriptor("https://youtu.be/example-video"),
            official: sourceDescriptor("https://example.com/research"),
            unsafe: sourceDescriptor("javascript:alert(1)")
          }));
        '''
        completed = subprocess.run(
            [node, '-e', script],
            check=True,
            capture_output=True,
            text=True,
            encoding='utf-8'
        )
        result = json.loads(completed.stdout)

        self.assertEqual(result['x']['href'], 'https://x.com/example/status/123')
        self.assertEqual(result['x']['label'], '在 X 查看原帖 ↗')
        self.assertEqual(result['youtube']['label'], '观看原始视频 ↗')
        self.assertEqual(result['official']['label'], '查看原始来源 ↗')
        self.assertIsNone(result['unsafe'])

    def test_history_scale_expands_recent_ai_years(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('Node.js is required to execute the history scale helper')

        template_path = Path(__file__).resolve().parents[1] / 'ai-roadmap.html'
        template = template_path.read_text(encoding='utf-8')
        helper_start = template.index('      const historyScale =')
        helper_end = template.index('      const setHistoryTrack =', helper_start)
        helper = template[helper_start:helper_end]
        script = helper + '''
          console.log(JSON.stringify({
            start: historyYearPosition(1943),
            web: historyYearPosition(1998),
            foundation: historyYearPosition(2021),
            current: historyYearPosition(2026),
            earlyYear: historyYearPosition(1980) - historyYearPosition(1979),
            recentYear: historyYearPosition(2025) - historyYearPosition(2024)
          }));
        '''
        completed = subprocess.run(
            [node, '-e', script],
            check=True,
            capture_output=True,
            text=True,
            encoding='utf-8'
        )
        result = json.loads(completed.stdout)

        self.assertEqual(result['start'], 16)
        self.assertEqual(result['web'], 28)
        self.assertEqual(result['foundation'], 69)
        self.assertEqual(result['current'], 96)
        self.assertGreater(result['recentYear'], result['earlyYear'] * 10)

    def test_public_history_chapter_requires_a_valid_source(self):
        data = load_roadmap_data(self.overlay)
        invalid_seed = deepcopy(data)
        invalid_seed['context_chapters'][0]['source_url'] = 'javascript:alert(1)'
        with self.assertRaises(RoadmapDataError):
            validate_seed(invalid_seed)

    def test_history_identity_media_requires_valid_urls(self):
        data = load_roadmap_data(self.overlay)

        invalid_person = deepcopy(data)
        invalid_person['history_people'][0]['image_url'] = 'not-a-url'
        with self.assertRaises(RoadmapDataError):
            validate_seed(invalid_person)

        invalid_organization = deepcopy(data)
        invalid_organization['history_organizations'][0]['logo_url'] = 'file:///logo.svg'
        with self.assertRaises(RoadmapDataError):
            validate_seed(invalid_organization)

    def test_missing_source_is_rejected(self):
        update = valid_update()
        del update['signals'][0]['source_url']
        with self.assertRaises(RoadmapDataError):
            persist_update(update, self.overlay)

    def test_incomplete_signal_is_rejected(self):
        update = valid_update()
        del update['signals'][0]['why_it_matters']
        with self.assertRaises(RoadmapDataError):
            persist_update(update, self.overlay)

    def test_builder_below_subscore_gate_is_rejected(self):
        update = valid_update()
        update['builders'][0]['breakdown'] = {
            'building': 23,
            'originality': 22,
            'relevance': 25,
            'source_quality': 10
        }
        with self.assertRaises(RoadmapDataError):
            persist_update(update, self.overlay)


if __name__ == '__main__':
    unittest.main()
