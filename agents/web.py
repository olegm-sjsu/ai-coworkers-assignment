"""HTTP, feed parsing, and article-text extraction. Standard library only."""
import email.utils
import hashlib
import html
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import timezone
from html.parser import HTMLParser
from pathlib import Path

UA = "Mozilla/5.0 (compatible; SJSU-AI-Coworkers/1.0; student project)"
ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "cache"


class _Follow308(urllib.request.HTTPRedirectHandler):
    """Python 3.9's urllib does not follow 308 redirects, and many documentation sites use them."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if code == 308:
            code = 301
        return super().redirect_request(req, fp, code, msg, headers, newurl)

    http_error_308 = urllib.request.HTTPRedirectHandler.http_error_302


_opener = urllib.request.build_opener(_Follow308)


def fetch(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with _opener.open(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def fetch_json(url, timeout=40):
    return json.loads(fetch(url, timeout))


def strip_tags(markup):
    text = re.sub(r"<(script|style)\b.*?</\1>", " ", markup or "", flags=re.S | re.I)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text))).strip()


def iso_date(value):
    value = (value or "").strip()
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        return parsed.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        pass
    match = re.match(r"\d{4}-\d{2}-\d{2}(T[\d:.]+(Z|[+-]\d{2}:?\d{2})?)?", value)
    if not match:
        return None
    stamp = match.group(0)
    return stamp if "T" in stamp else stamp + "T12:00:00+00:00"


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _child_text(node, *names):
    for child in node:
        if _local(child.tag) in names and (child.text or "").strip():
            return child.text.strip()
    return ""


def parse_feed(xml_text):
    """Return [{title, url, published, summary}] from RSS 2.0 or Atom."""
    try:
        root = ET.fromstring(xml_text.encode("utf-8"))
    except ET.ParseError:
        # Some feeds carry raw control characters or bare ampersands. Repair those and try once more.
        cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", xml_text)
        cleaned = re.sub(r"&(?!#?\w+;)", "&amp;", cleaned)
        root = ET.fromstring(cleaned.encode("utf-8"))
    items = []
    for node in root.iter():
        kind = _local(node.tag)
        if kind not in ("item", "entry"):
            continue
        url = _child_text(node, "link")
        if not url:
            for child in node:
                if _local(child.tag) == "link" and child.get("rel", "alternate") == "alternate":
                    url = child.get("href", "")
                    break
        published = iso_date(_child_text(node, "pubDate", "published", "updated", "date"))
        title = strip_tags(_child_text(node, "title"))
        if title and url and published:
            items.append({"title": title, "url": url.strip(), "published": published,
                          "summary": strip_tags(_child_text(node, "description", "summary", "encoded", "content"))[:2000]})
    return items


class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "nav", "header", "footer", "aside", "form", "noscript", "svg", "button"}
    BLOCK = {"p", "h1", "h2", "h3", "h4", "li", "pre", "blockquote", "tr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.scopes = {"all": [], "main": [], "article": []}
        self.inside = {"main": 0, "article": 0}

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        if tag in self.inside:
            self.inside[tag] += 1
        if tag in self.BLOCK:
            self._add("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        if tag in self.inside and self.inside[tag]:
            self.inside[tag] -= 1

    def handle_data(self, data):
        if not self.skip:
            self._add(data)

    def _add(self, text):
        self.scopes["all"].append(text)
        for scope, depth in self.inside.items():
            if depth:
                self.scopes[scope].append(text)


def extract_text(markup):
    parser = _TextExtractor()
    parser.feed(markup)
    for scope in ("article", "main", "all"):
        text = "".join(parser.scopes[scope])
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\s*\n\s*", "\n", text).strip()
        if len(text.split()) >= 150 or scope == "all":
            return text
    return ""


def article_text(url):
    """Fetch and cache one article's readable text. Returns (text, status)."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / (hashlib.sha1(url.encode()).hexdigest() + ".txt")
    if path.exists():
        return path.read_text(), "ok"
    try:
        # An arXiv abstract page is too thin to summarise, so prefer the HTML paper when it exists.
        paper = re.match(r"https?://arxiv\.org/abs/(.+)", url)
        try:
            text = extract_text(fetch(f"https://arxiv.org/html/{paper.group(1)}")) if paper else extract_text(fetch(url))
        except Exception:
            if not paper:
                raise
            text = extract_text(fetch(url))
    except Exception as exc:  # network failures are data: the article becomes ineligible
        return "", f"{type(exc).__name__}: {exc}"[:120]
    if len(text.split()) >= 150:
        path.write_text(text)
    return text, "ok"
