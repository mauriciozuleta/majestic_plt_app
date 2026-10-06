"""Reader for the U.S. Commercial Service's Country Commercial Guides
(https://www.trade.gov/country-commercial-guides) — market conditions,
opportunities and import regulations, written at U.S. embassies. ITA's API
no longer serves these guides (Country Commercial Guides and Market
Intelligence aren't among its current APIs), so they're read from the public
chapter pages, which need no key.

A guide is a set of chapter pages named /country-commercial-guides/
<country-slug>-<chapter> (jamaica-import-tariffs, ...); each page links to
all of its guide's chapters, and its text sits in the page's `node-content`
block (the rest is navigation, a chatbot disclaimer and the footer). Not
every country has a guide (Saint Lucia doesn't) — `fetch_guide` returns None
for those.

Used by the Country Commercial Profile build (routers/country_profile.py),
which takes the guide as its primary source.
"""

import re
from html.parser import HTMLParser

import httpx

from ..custom_sources.extract import USER_AGENT, _ssl_context

BASE_URL = 'https://www.trade.gov/country-commercial-guides'

# The chapters the profile is built from, by its two focuses — opportunities
# for our products, and the rules for importing food — in reading order, each
# matched by how its page name STARTS: guides name the same chapter
# differently, typos included ("market-opportunites", "import-tariff",
# "labelingmarking-requirements", "agricultural-sectors", "customs-laws-and-
# regulations"). A guide that lacks one simply goes without it.
PROFILE_CHAPTERS = [
    'market-overview',
    'market-opportun',
    'agricultur',
    'import-tariff',
    'import-requirements',
    'labeling',
    'standards',
    'prohibited',
    'customs',
    'trade-agreements',
]
_EDGE_JUNK = re.compile(r'^[\s​‌‍⁠﻿�]+|[\s​‌‍⁠﻿�]+$')
# Keeps one very long chapter from crowding the others out of the prompt.
MAX_CHAPTER_CHARS = 14000

_BLOCK_TAGS = {'p', 'div', 'section', 'article', 'table', 'tr', 'ul', 'ol', 'br', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li'}
_HEADINGS = {'h1': '# ', 'h2': '## ', 'h3': '### ', 'h4': '#### ', 'h5': '#### ', 'h6': '#### '}
_VOID = {'br', 'img', 'meta', 'link', 'input', 'hr', 'source', 'wbr'}


def country_slug(country_name: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', country_name.lower().replace('&', 'and')).strip('-')


class _ChapterText(HTMLParser):
    """Text of the page's `node-content` block, with headings, list items
    and table cells kept readable."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0  # >0 while inside node-content (counts open tags inside it)
        self.skip = 0  # >0 while inside script/style
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in _VOID:
            if self.depth and tag == 'br':
                self.parts.append('\n')
            return
        classes = (dict(attrs).get('class') or '').split()
        if self.depth:
            self.depth += 1
            if tag in ('script', 'style'):
                self.skip += 1
            elif tag in _HEADINGS:
                self.parts.append('\n\n' + _HEADINGS[tag])
            elif tag == 'li':
                self.parts.append('\n- ')
            elif tag in ('td', 'th'):
                self.parts.append(' | ')
            elif tag in _BLOCK_TAGS:
                self.parts.append('\n')
        elif 'node-content' in classes:
            self.depth = 1

    def handle_endtag(self, tag):
        if tag in _VOID or not self.depth:
            return
        if tag in ('script', 'style') and self.skip:
            self.skip -= 1
        if tag in _BLOCK_TAGS:
            self.parts.append('\n')
        self.depth -= 1

    def handle_data(self, data):
        if self.depth and not self.skip:
            self.parts.append(data)

    def text(self) -> str:
        text = ''.join(self.parts).replace('\xa0', ' ')
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r' *\n *', '\n', text)
        # node-content opens with the guide's chapter menu; the chapter itself
        # starts after its "Last published date: ..." line.
        start = re.search(r'^Last published date:.*$', text, re.M)
        if start:
            text = text[start.end():]
        # ...and ends where the site's AI-chatbot notice is appended.
        end = re.search(r'^#+ Global Business Navigator Chatbot', text, re.M)
        if end:
            text = text[: end.start()]
        return _EDGE_JUNK.sub('', re.sub(r'\n{3,}', '\n\n', text))


def _published(html: str) -> str | None:
    match = re.search(r'Last published date[^<]*(?:<[^>]+>\s*)*([A-Z][a-z]+ \d{1,2}, \d{4}|\d{4}-\d{2}-\d{2})', html)
    return match.group(1) if match else None


def _title(html: str) -> str:
    match = re.search(r'<title>([^<|]+)', html)
    return re.sub(r'\s+', ' ', match.group(1)).strip() if match else ''


def fetch_guide(country_name: str, chapters: list[str] = PROFILE_CHAPTERS) -> dict | None:
    """{country, slug, published, url, chapters: [{key, title, url, text}]}
    for the guide's chapters matching `chapters` (page-name prefixes) that
    exist, or None when the country has no guide. Network errors other than
    "no such guide" raise."""
    slug = country_slug(country_name)
    with httpx.Client(timeout=40, follow_redirects=True, headers={'User-Agent': USER_AGENT}, verify=_ssl_context()) as client:
        overview = client.get(f'{BASE_URL}/{slug}-market-overview')
        if overview.status_code == 404:
            return None
        overview.raise_for_status()
        available = sorted(set(re.findall(rf'href="/country-commercial-guides/{re.escape(slug)}-([a-z0-9-]+)"', overview.text)))
        found = []
        published = _published(overview.text)
        for prefix in chapters:
            key = 'market-overview' if prefix == 'market-overview' else next((name for name in available if name.startswith(prefix)), None)
            if key is None:
                continue
            if key == 'market-overview':
                response = overview
            else:
                response = client.get(f'{BASE_URL}/{slug}-{key}')
                if response.status_code == 404:
                    continue
                response.raise_for_status()
            parser = _ChapterText()
            parser.feed(response.text)
            text = parser.text()
            if not text:
                continue
            if len(text) > MAX_CHAPTER_CHARS:
                text = text[:MAX_CHAPTER_CHARS].rsplit('\n', 1)[0] + '\n[… chapter shortened]'
            found.append({'key': key, 'title': _title(response.text) or key.replace('-', ' ').title(), 'url': str(response.url), 'text': text})
            published = published or _published(response.text)
    if not found:
        return None
    return {'country': country_name, 'slug': slug, 'published': published, 'url': f'{BASE_URL}/{slug}-market-overview', 'chapters': found}
