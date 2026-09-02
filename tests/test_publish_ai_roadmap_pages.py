import unittest

from scripts.publish_ai_roadmap_pages import PagesPublishError, prepare_public_html


SAMPLE_HTML = '''<!doctype html>
<html lang="zh-CN">
<head>
  <script>document.documentElement.dataset.theme = "light";</script>
  <title>AI Builder Roadmap</title>
</head>
<body data-design-system="midnight-atlas-paper">
  <a class="brand" href="/ai-roadmap">Roadmap</a>
  <a class="top-link optional" href="/">Memory</a>
  <a class="top-link optional" href="/space">Space</a>
  <main>Weekly public signal</main>
</body>
</html>
'''


class PagesPublisherTests(unittest.TestCase):
    def test_public_page_removes_local_navigation_and_adds_metadata(self):
        page, version = prepare_public_html(
            SAMPLE_HTML,
            'https://example.github.io/roadmap/',
        )

        self.assertIn('<a class="brand" href="./">Roadmap</a>', page)
        self.assertNotIn('href="/"', page)
        self.assertNotIn('href="/space"', page)
        self.assertNotIn('href="/ai-roadmap"', page)
        self.assertIn('data-hosting="github-pages"', page)
        self.assertIn(
            '<link rel="canonical" href="https://example.github.io/roadmap/">',
            page,
        )
        self.assertIn(f'name="ai-roadmap-version" content="{version}"', page)
        self.assertIn('Weekly public signal', page)

    def test_public_page_rejects_unrendered_template(self):
        with self.assertRaises(PagesPublishError):
            prepare_public_html(SAMPLE_HTML.replace('Weekly public signal', '__AI_ROADMAP_DATA__'))

    def test_public_page_requires_https_site_url(self):
        with self.assertRaises(PagesPublishError):
            prepare_public_html(SAMPLE_HTML, 'http://example.com/roadmap/')


if __name__ == '__main__':
    unittest.main()
