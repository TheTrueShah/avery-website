"""Load the Avery constitution and search it by section.

No Discord imports here, so this can be tested on its own:
    python3 constitution.py room picks
"""
import re
import ssl
import sys
import urllib.request

try:  # Python from python.org on macOS ships without root certificates
    import certifi
    _SSL = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL = None

SOURCE = 'https://raw.githubusercontent.com/averyhouse/constitution/master/constitution.md'
SITE = 'https://avery.caltech.edu/constitution/'

HEADING = re.compile(r'^(#{1,6})\s+(.*?)\s*$')


def pandoc_id(title, seen):
    """The anchor pandoc generates for a heading, so links land on the right
    spot of the website's constitution page."""
    text = re.sub(r'[^\w\s.\-]', '', title.lower())
    text = re.sub(r'\s+', '-', text.strip())
    text = re.sub(r'^[^a-z]+', '', text) or 'section'
    if text in seen:
        n = 1
        while f'{text}-{n}' in seen:
            n += 1
        text = f'{text}-{n}'
    seen.add(text)
    return text


class Section:
    def __init__(self, level, title, anchor):
        self.level, self.title, self.anchor = level, title, anchor
        self.lines = []

    @property
    def body(self):
        return re.sub(r'\s+', ' ', ' '.join(self.lines)).strip()

    @property
    def url(self):
        return SITE + '#' + self.anchor

    def excerpt(self, words, width=320):
        body = self.body
        if not body:
            return ''
        low = body.lower()
        hits = [low.find(w) for w in words if low.find(w) != -1]
        start = max(0, min(hits) - 80) if hits else 0
        if start:
            start = body.find(' ', start) + 1
        text = body[start:start + width]
        if start + width < len(body):
            text = text.rsplit(' ', 1)[0] + ' …'
        return ('… ' if start else '') + text


class Constitution:
    def __init__(self):
        self.sections = []

    def load_text(self, markdown):
        sections, seen, current = [], set(), None
        for line in markdown.splitlines():
            m = HEADING.match(line)
            if m:
                current = Section(len(m.group(1)), m.group(2), pandoc_id(m.group(2), seen))
                sections.append(current)
            elif current is not None:
                current.lines.append(line)
        self.sections = sections
        return len(sections)

    def refresh(self, source=SOURCE, timeout=20):
        """Fetch the latest constitution from GitHub. Raises on network errors."""
        with urllib.request.urlopen(source, timeout=timeout, context=_SSL) as r:
            return self.load_text(r.read().decode('utf-8'))

    def search(self, query, limit=3):
        words = [w for w in re.findall(r'[\w.]+', query.lower()) if len(w) > 1]
        if not words:
            return []
        scored = []
        for s in self.sections:
            title, body = s.title.lower(), s.body.lower()
            if not all(w in title or w in body for w in words):
                continue
            score = sum(10 * (w in title) + body.count(w) for w in words)
            scored.append((score, s))
        scored.sort(key=lambda pair: -pair[0])
        return [(s, s.excerpt(words)) for _, s in scored[:limit]]


if __name__ == '__main__':
    c = Constitution()
    print(c.refresh(), 'sections loaded')
    for section, excerpt in c.search(' '.join(sys.argv[1:]) or 'room picks'):
        print(f'\n{section.title}\n{section.url}\n{excerpt}')
