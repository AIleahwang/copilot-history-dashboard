#!/usr/bin/env python
"""Publish the rendered AI Builder Roadmap as a GitHub Pages site."""

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen


DEFAULT_HTML = Path.home() / '.follow-builders' / 'ai-builder-roadmap.html'
DEFAULT_REPOSITORY = 'AIleahwang/copilot-history-dashboard'
DEFAULT_BRANCH = 'gh-pages'
DEFAULT_SITE_URL = 'https://aileahwang.github.io/copilot-history-dashboard/'
DEFAULT_GITHUB_USER = 'AIleahwang'
LOCAL_NAVIGATION_PATTERN = re.compile(
    r'<a class="top-link optional" href="/(?:|space)">.*?</a>',
    re.DOTALL,
)


class PagesPublishError(RuntimeError):
    """Raised when a public roadmap cannot be prepared or published."""


def _validate_site_url(site_url):
    parsed = urlparse(site_url)
    if parsed.scheme != 'https' or not parsed.netloc:
        raise PagesPublishError('site URL must be an absolute https URL')
    return site_url.rstrip('/') + '/'


def prepare_public_html(source, site_url=DEFAULT_SITE_URL):
    """Remove local-only navigation and add deployment metadata."""
    site_url = _validate_site_url(site_url)
    if not isinstance(source, str) or not source.lstrip().lower().startswith('<!doctype html>'):
        raise PagesPublishError('roadmap input must be a complete HTML document')
    if '__AI_ROADMAP_DATA__' in source:
        raise PagesPublishError('roadmap input still contains the unresolved data marker')
    if '<body' not in source or '</head>' not in source:
        raise PagesPublishError('roadmap input is missing required document elements')

    version = hashlib.sha256(source.encode('utf-8')).hexdigest()
    public_html = LOCAL_NAVIGATION_PATTERN.sub('', source)
    public_html = public_html.replace(
        '<a class="brand" href="/ai-roadmap"',
        '<a class="brand" href="./"',
        1,
    )
    public_html = public_html.replace(
        '<body ',
        '<body data-hosting="github-pages" ',
        1,
    )
    metadata = (
        '  <meta name="description" content="AI Builder Scout weekly signals, '
        'AI evolution atlas, original sources, and opportunity hypotheses.">\n'
        f'  <meta name="ai-roadmap-version" content="{version}">\n'
        f'  <link rel="canonical" href="{site_url}">\n'
    )
    public_html = public_html.replace('</head>', metadata + '</head>', 1)

    forbidden_links = ('href="/"', 'href="/space"', 'href="/ai-roadmap"')
    if any(link in public_html for link in forbidden_links):
        raise PagesPublishError('public roadmap still contains local-only navigation')
    return public_html, version


def _github_environment(user):
    if not shutil.which('gh'):
        raise PagesPublishError('GitHub CLI is required to publish the roadmap')
    completed = subprocess.run(
        ['gh', 'auth', 'token', '--user', user],
        check=False,
        capture_output=True,
        text=True,
        encoding='utf-8',
    )
    token = completed.stdout.strip()
    if completed.returncode or not token:
        raise PagesPublishError(f'GitHub CLI has no usable login for {user}')
    environment = os.environ.copy()
    environment['GH_TOKEN'] = token
    return environment


def _gh_api(endpoint, environment, method='GET', payload=None, allow_not_found=False):
    command = ['gh', 'api', endpoint, '--method', method]
    input_text = None
    if payload is not None:
        command.extend(['--input', '-'])
        input_text = json.dumps(payload, separators=(',', ':'))
    completed = subprocess.run(
        command,
        input=input_text,
        check=False,
        capture_output=True,
        text=True,
        encoding='utf-8',
        env=environment,
    )
    output = (completed.stdout or '').strip()
    errors = (completed.stderr or '').strip()
    if completed.returncode:
        if allow_not_found and ('HTTP 404' in errors or '"status":"404"' in output):
            return None
        detail = errors or output or f'exit code {completed.returncode}'
        raise PagesPublishError(f'GitHub API request failed: {detail}')
    return json.loads(output) if output else {}


def _ensure_branch(repository, branch, environment):
    branch_ref = f'repos/{repository}/git/ref/heads/{quote(branch, safe="")}'
    current = _gh_api(branch_ref, environment, allow_not_found=True)
    if current:
        return current['object']['sha']

    repository_info = _gh_api(f'repos/{repository}', environment)
    default_branch = repository_info['default_branch']
    source = _gh_api(
        f'repos/{repository}/git/ref/heads/{quote(default_branch, safe="")}',
        environment,
    )
    source_sha = source['object']['sha']
    _gh_api(
        f'repos/{repository}/git/refs',
        environment,
        method='POST',
        payload={'ref': f'refs/heads/{branch}', 'sha': source_sha},
    )
    return source_sha


def _git_blob_sha(content):
    payload = content.encode('utf-8')
    header = f'blob {len(payload)}\0'.encode('ascii')
    return hashlib.sha1(header + payload).hexdigest()


def _put_file(repository, branch, path, content, message, environment):
    encoded_path = quote(path, safe='/')
    endpoint = f'repos/{repository}/contents/{encoded_path}'
    existing = _gh_api(
        f'{endpoint}?ref={quote(branch, safe="")}',
        environment,
        allow_not_found=True,
    )
    if existing and existing.get('sha') == _git_blob_sha(content):
        return False

    payload = {
        'message': message,
        'content': base64.b64encode(content.encode('utf-8')).decode('ascii'),
        'branch': branch,
    }
    if existing:
        payload['sha'] = existing['sha']
    _gh_api(endpoint, environment, method='PUT', payload=payload)
    return True


def _ensure_pages(repository, branch, environment):
    endpoint = f'repos/{repository}/pages'
    pages = _gh_api(endpoint, environment, allow_not_found=True)
    if pages:
        source = pages.get('source') or {}
        if source.get('branch') != branch or source.get('path') != '/':
            raise PagesPublishError(
                f'GitHub Pages already uses {source.get("branch")}:{source.get("path")}'
            )
        return pages['html_url'].rstrip('/') + '/'

    pages = _gh_api(
        endpoint,
        environment,
        method='POST',
        payload={'source': {'branch': branch, 'path': '/'}},
    )
    return pages.get('html_url', DEFAULT_SITE_URL).rstrip('/') + '/'


def _wait_for_deployment(site_url, version, timeout_seconds):
    deadline = time.monotonic() + timeout_seconds
    marker = f'name="ai-roadmap-version" content="{version}"'
    last_error = 'site did not respond'
    while time.monotonic() < deadline:
        separator = '&' if '?' in site_url else '?'
        request = Request(
            f'{site_url}{separator}version={version[:12]}',
            headers={'User-Agent': 'AI-Builder-Roadmap-Publisher'},
        )
        try:
            with urlopen(request, timeout=20) as response:
                content = response.read().decode('utf-8', errors='replace')
                if response.status == 200 and marker in content:
                    return
                last_error = f'HTTP {response.status} returned an older deployment'
        except (HTTPError, URLError, TimeoutError) as exc:
            last_error = str(exc)
        time.sleep(5)
    raise PagesPublishError(
        f'GitHub Pages did not serve version {version[:12]} within '
        f'{timeout_seconds} seconds: {last_error}'
    )


def publish(
    html_path=DEFAULT_HTML,
    repository=DEFAULT_REPOSITORY,
    branch=DEFAULT_BRANCH,
    site_url=DEFAULT_SITE_URL,
    github_user=DEFAULT_GITHUB_USER,
    wait_seconds=300,
):
    html_path = Path(html_path)
    try:
        source = html_path.read_text(encoding='utf-8')
    except OSError as exc:
        raise PagesPublishError(f'cannot read rendered roadmap: {html_path}') from exc
    public_html, version = prepare_public_html(source, site_url)
    environment = _github_environment(github_user)
    _ensure_branch(repository, branch, environment)
    changed = _put_file(
        repository,
        branch,
        'index.html',
        public_html,
        f'Publish AI Builder Roadmap {version[:12]}',
        environment,
    )
    _put_file(
        repository,
        branch,
        '.nojekyll',
        '',
        'Configure static GitHub Pages',
        environment,
    )
    published_url = _ensure_pages(repository, branch, environment)
    if wait_seconds:
        _wait_for_deployment(published_url, version, wait_seconds)
    return {
        'url': published_url,
        'version': version,
        'changed': changed,
        'bytes': len(public_html.encode('utf-8')),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--html', default=str(DEFAULT_HTML), help='Rendered roadmap HTML')
    parser.add_argument('--repo', default=DEFAULT_REPOSITORY, help='GitHub owner/repository')
    parser.add_argument('--branch', default=DEFAULT_BRANCH, help='Pages source branch')
    parser.add_argument('--site-url', default=DEFAULT_SITE_URL, help='Expected public URL')
    parser.add_argument('--github-user', default=DEFAULT_GITHUB_USER, help='GitHub CLI login')
    parser.add_argument(
        '--wait-seconds',
        type=int,
        default=300,
        help='Seconds to wait for the published version; use 0 to skip',
    )
    parser.add_argument('--check', action='store_true', help='Prepare and validate only')
    args = parser.parse_args()

    try:
        source = Path(args.html).read_text(encoding='utf-8')
        public_html, version = prepare_public_html(source, args.site_url)
        if args.check:
            print(
                f'valid public roadmap: version={version[:12]} '
                f'bytes={len(public_html.encode("utf-8"))}'
            )
            return 0
        result = publish(
            html_path=args.html,
            repository=args.repo,
            branch=args.branch,
            site_url=args.site_url,
            github_user=args.github_user,
            wait_seconds=max(0, args.wait_seconds),
        )
        status = 'updated' if result['changed'] else 'unchanged'
        print(
            f'published AI roadmap: {result["url"]} '
            f'version={result["version"][:12]} status={status}'
        )
        return 0
    except (OSError, PagesPublishError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
