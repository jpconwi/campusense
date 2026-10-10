"""
services/nemsu_collector.py - collects PUBLIC, official NEMSU announcements into the
knowledge_documents table (Phase 1 of the NEMSU knowledge base).

Sources (each one is a small function, so Facebook / PDFs can be added later):
  nemsu_news  https://nemsu.edu.ph/news      the Newsroom (pages: /news?page=2 ...)
  nemsu_memo  https://memo.nemsu.edu.ph      memorandums (a WordPress site -> its JSON API,
                                              with an HTML fallback)

How one sync works
  1. read the list pages, 2. skip URLs that are already saved, 3. open each NEW article,
  4. clean the text, 5. save title / content / date / url.
The collector is polite: it reads robots.txt, waits between requests, identifies itself,
and only reads a few pages per run. It never logs in and never touches private pages.
"""

import hashlib
import html as html_lib
import json
import re
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from urllib import robotparser
from urllib.parse import quote, unquote, urljoin, urlsplit, urlunsplit

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import config
from app.models import KnowledgeDocument

NEWS = "nemsu_news"
MEMO = "nemsu_memo"
USER_AGENT = "Mozilla/5.0 (compatible; NEMSAI-Collector/1.0; NEMSU student project; public pages only)"

_MONTHS = ("January|February|March|April|May|June|July|August|September|October|"
           "November|December")
_DATE = re.compile(rf"\b({_MONTHS})\s+(\d{{1,2}}),\s*(\d{{4}})\b", re.I)
_BYLINE = re.compile(rf"^by:\s*(?P<author>.+?)\s*\|\s*(?P<date>(?:{_MONTHS})\s+\d{{1,2}},\s*\d{{4}})\s*$",
                     re.I)
# "Public Information Office | February 26, 2025" (no "by:") = a LINK TO ANOTHER ARTICLE in a sidebar
_SIDE = re.compile(rf"^(?!by:)[^|]{{2,120}}\|\s*(?:{_MONTHS})\s+\d{{1,2}},\s*\d{{4}}$", re.I)
_STOP = re.compile(r"^(read more|related (news|posts|articles)|more news|latest news|"
                   r"recent news|share( this)?|back to news)\b", re.I)
_NOISE_TAGS = ["script", "style", "noscript", "svg", "nav", "header", "footer", "aside",
               "form", "iframe", "button"]


class CollectorError(Exception):
    pass


@dataclass
class CollectedDoc:
    title: str
    content: str
    source_url: str
    published_at: "datetime | None"
    source_type: str
    author: "str | None" = None


# ------------------------------------------------------------------ text helpers
_MOJIBAKE = re.compile("[\u00c2\u00c3\u00e2\u00f0][\u0080-\u00ff\u0152\u0153\u0160\u0161\u0178\u017d\u017e\u0192\u02c6\u02dc\u2013-\u203a\u20ac\u2122]")


def _byte_of(ch):
    """The byte that Windows-1252 (or Latin-1 for its 5 empty slots) shows as this character."""
    try:
        return ch.encode("cp1252")
    except UnicodeEncodeError:
        return ch.encode("latin-1") if ord(ch) < 256 else None


def fix_mojibake(text):
    """Repair text that was UTF-8 but got read as Windows-1252, e.g. 'â€"' -> a dash and
    the bold 'ð...' blocks -> the real bold letters. Text that is already fine is returned as is."""
    if not text or not _MOJIBAKE.search(text):
        return text
    out, buf = [], bytearray()

    def flush():
        if buf:
            out.append(bytes(buf).decode("utf-8", errors="replace"))
            buf.clear()

    for ch in text:
        raw = _byte_of(ch) if ord(ch) > 127 else None
        if raw is not None:
            buf.extend(raw)
        else:
            flush()
            out.append(ch)
    flush()
    fixed = "".join(out)
    return text if "\ufffd" in fixed and "\ufffd" not in text else fixed


def clean_text(text):
    """Plain text: fancy Unicode letters become normal ones (NFKC turns the bold
    'North' that NEMSU's Facebook-style titles use into 'North'), blank space tidied."""
    text = unicodedata.normalize("NFKC", fix_mojibake(text or "")).replace("\xa0", " ")
    out, blank = [], False
    for line in text.splitlines():
        line = re.sub(r"[ \t]+", " ", line).strip()
        if line:
            out.append(line)
            blank = False
        elif out and not blank:
            out.append("")
            blank = True
    return "\n".join(out).strip()


def parse_date(text):
    """'... April 26, 2024 ...' -> datetime, or None."""
    m = _DATE.search(text or "")
    if not m:
        return None
    try:
        return datetime.strptime(f"{m.group(1).title()} {m.group(2)} {m.group(3)}", "%B %d %Y")
    except ValueError:
        return None


def parse_iso(value):
    """'2026-09-11T10:30:00', '...Z', '...+08:00' -> naive datetime, or None."""
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return parse_date(value)


def _host_key(host):
    host = host.lower()
    for prefix in ("www.", "mail."):
        if host.startswith(prefix):
            return host[len(prefix):]
    return host


def canonical_url(href, base, relative_to=None):
    """One stable address per page, so the same article is never saved twice:
    https, the main host (www./mail. removed), '/index.php' removed, no #fragment,
    no ?query, no trailing slash, path percent-encoded the same way every time."""
    absolute = urljoin((relative_to or base) + ("/" if not relative_to else ""), href)
    parts = urlsplit(absolute)
    base_host = urlsplit(base).netloc.lower()
    host = parts.netloc.lower()
    if _host_key(host) == _host_key(base_host):
        host = base_host
    path = parts.path
    if path.startswith("/index.php/"):
        path = path[len("/index.php"):]
    path = quote(unquote(path), safe="/-_.~:@!$&'()*+,;=")
    path = path.rstrip("/") or "/"
    return urlunsplit(("https", host, path, "", ""))


def _same_site(url, base):
    return _host_key(urlsplit(url).netloc) == _host_key(urlsplit(base).netloc)


# ------------------------------------------------------------------ HTTP (polite)
class Fetcher:
    """httpx wrapper: identifies itself, waits between requests, obeys robots.txt."""

    def __init__(self, client=None, delay=None, timeout=None):
        self._own = client is None
        read = timeout or config.NEMSU_COLLECT_TIMEOUT
        self.client = client or httpx.Client(
            headers={"User-Agent": USER_AGENT,
                     "Accept": "text/html,application/xhtml+xml,application/json,application/xml"},
            timeout=httpx.Timeout(connect=10.0, read=read, write=10.0, pool=10.0),
            transport=httpx.HTTPTransport(retries=2),          # retry slow/failed connections
            follow_redirects=True)
        self.delay = config.NEMSU_COLLECT_DELAY if delay is None else delay
        self._last = 0.0
        self._robots = {}

    def close(self):
        if self._own:
            self.client.close()

    def _allowed(self, url):
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            parser = robotparser.RobotFileParser()
            try:
                r = self.client.get(origin + "/robots.txt")
                parser.parse(r.text.splitlines() if r.status_code == 200 else [])
            except httpx.HTTPError:
                parser.parse([])               # robots.txt unreachable -> nothing is blocked
            self._robots[origin] = parser
        return self._robots[origin].can_fetch(USER_AGENT, url)

    def get(self, url, params=None):
        if not self._allowed(url):
            raise CollectorError(f"robots.txt does not allow reading {url}")
        wait = self.delay - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        try:
            r = self.client.get(url, params=params)
        finally:
            self._last = time.monotonic()
        r.raise_for_status()
        return r



# ------------------------------------------------------------------ pages built by JavaScript
def _looks_js_rendered(html):
    markers = ('data-page=', "__NEXT_DATA__", "__NUXT__", 'id="app"', 'id="root"', "window.__")
    return any(m in (html or "") for m in markers)


def _no_links_note(url, response):
    text = response.text or ""
    note = (f"{url}: HTTP {response.status_code}, {len(text)} bytes, but no article links "
            f"(/news/<name>) were found")
    if _looks_js_rendered(text):
        note += " - the page looks like it is built by JavaScript"
    if re.search(r"just a moment|cf-chl|challenge-platform|captcha", text, re.I):
        note += " - it looks like a bot-protection page"
    return note + ". Run: python -m scripts.nemsu_probe"


def _walk(obj):
    """Every dict inside nested JSON."""
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)


def _page_json(soup):
    """The page data of an Inertia.js site. Older versions keep it in a data-page="{...}"
    attribute; newer ones in <script data-page="app" type="application/json">{...}</script>.
    Several tags can carry data-page, so every one is tried until one gives real data."""
    for el in soup.find_all(attrs={"data-page": True}):
        for text in (el.get_text() or "", el.get("data-page") or ""):
            try:
                data = json.loads(text)
            except (ValueError, TypeError):
                continue
            if isinstance(data, dict) and ("props" in data or "component" in data):
                return data
    return None


_TITLE_KEYS = ("title", "name", "headline", "news_title")
_LINK_KEYS = ("url", "link", "href", "permalink", "path", "route", "show_url", "news_url")
_SLUG_KEYS = ("slug", "news_slug", "url_slug", "alias")


def _item_url(d, base):
    """The /news/<name> address of one JSON item, or None."""
    if not any(isinstance(d.get(k), str) and d[k].strip() for k in _TITLE_KEYS):
        return None
    for key in _LINK_KEYS:
        value = d.get(key)
        if isinstance(value, str) and "/news/" in value:
            return canonical_url(value, base)
    for key in _SLUG_KEYS:
        value = d.get(key)
        if isinstance(value, str) and value.strip():
            return canonical_url("/news/" + value.strip("/"), base)
    return None


def _urls_from_page_json(soup, base):
    urls = []
    for d in _walk(_page_json(soup)):
        url = _item_url(d, base)
        if url:
            urls.append(url)
    return urls


def _exact_article_from_page_json(soup):
    """nemsu.edu.ph (Inertia): the real article is props.article.contentHtml. Returns
    (content, author, published) or None."""
    data = _page_json(soup)
    props = data.get("props") if isinstance(data, dict) else None
    art = props.get("article") if isinstance(props, dict) else None
    if not (isinstance(art, dict) and isinstance(art.get("contentHtml"), str) and art["contentHtml"].strip()):
        return None
    text = clean_text(BeautifulSoup(html_lib.unescape(art["contentHtml"]), "html.parser").get_text("\n"))
    office = art.get("office") if isinstance(art.get("office"), str) else None
    published = None
    raw = str(art.get("date") or "").strip()
    for fmt in ("%b %d, %Y", "%B %d, %Y"):                      # the site writes 'Sep 1, 2025'
        try:
            published = datetime.strptime(raw, fmt)
            break
        except ValueError:
            pass
    return text, office, published or parse_date(raw)


def _article_from_page_json(soup):
    """(content, author, published) taken from the page's JSON data, or None."""
    data = _page_json(soup)
    best = None
    for d in _walk(data):
        if not isinstance(d.get("title"), str):
            continue
        for key in ("content", "body", "description", "details", "text", "excerpt"):
            value = d.get(key)
            if isinstance(value, str) and (best is None or len(value) > len(best[0])):
                author = d.get("author")
                author = author.get("name") if isinstance(author, dict) else author
                published = (d.get("published_at") or d.get("created_at") or d.get("date")
                             or d.get("posted_at"))
                best = (value, author if isinstance(author, str) else None, published)
    if not best:
        return None
    text = clean_text(BeautifulSoup(html_lib.unescape(best[0]), "html.parser").get_text("\n"))
    return text, best[1], parse_iso(str(best[2])) if best[2] else None


def _urls_from_sitemap(fetcher, base):
    """/news/<name> addresses listed in sitemap.xml (newest first when it has lastmod)."""
    found, queue, checked = {}, [base + "/sitemap.xml"], 0
    while queue and checked < 6:
        checked += 1
        xml = fetcher.get(queue.pop(0)).text
        for block in re.findall(r"<(?:url|sitemap)>(.*?)</(?:url|sitemap)>", xml, re.S):
            loc = re.search(r"<loc>\s*(.*?)\s*</loc>", block, re.S)
            if not loc:
                continue
            loc = html_lib.unescape(loc.group(1))
            if loc.endswith(".xml"):
                queue.append(loc)
                continue
            url = canonical_url(loc, base)
            if _same_site(url, base) and re.fullmatch(r"/news/[^/]+", urlsplit(url).path):
                mod = re.search(r"<lastmod>\s*(.*?)\s*</lastmod>", block, re.S)
                found[url] = (mod.group(1) if mod else "")
    return sorted(found, key=lambda u: found[u], reverse=True)


def _urls_from_feeds(fetcher, base):
    """/news/<name> addresses listed in an RSS/Atom feed, if the site has one."""
    urls = []
    for path in ("/feed", "/rss", "/rss.xml", "/feed.xml", "/news/feed", "/news/rss"):
        try:
            xml = fetcher.get(base + path).text
        except (httpx.HTTPError, CollectorError):
            continue
        for link in re.findall(r"<link[^>]*>\s*(https?://[^<\s]+)\s*</link>|<link[^>]*href=\"([^\"]+)\"", xml):
            url = canonical_url(link[0] or link[1], base)
            if _same_site(url, base) and re.fullmatch(r"/news/[^/]+", urlsplit(url).path):
                urls.append(url)
        if urls:
            break
    return list(dict.fromkeys(urls))

# ------------------------------------------------------------------ source 1: Newsroom
def parse_news_list(html, page_url, base):
    """All article links on a list page: addresses shaped like /news/<slug>.
    Looks at normal links first, then at links hidden in scripts / JSON data."""
    soup = BeautifulSoup(html, "html.parser")
    urls, seen = [], set()

    def add(href):
        url = canonical_url(href, base, relative_to=page_url)
        if (_same_site(url, base) and re.fullmatch(r"/news/[^/]+", urlsplit(url).path)
                and url not in seen):
            seen.add(url)
            urls.append(url)

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href and not href.startswith(("#", "mailto:", "tel:", "javascript:")):
            add(href)
    for url in _urls_from_page_json(soup, base):
        add(url)
    raw = html_lib.unescape((html or "").replace("\\/", "/"))
    for href in re.findall(r"""(?:https?://[^\s"'<>\\]+)?/news/[^\s"'<>\\)?#/]+""", raw):
        add(href)
    return urls


def _meta(soup, *names):
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            return tag["content"]
    return ""


def _published_from_page(soup):
    value = _meta(soup, "article:published_time", "og:article:published_time", "datePublished")
    if not value:
        t = soup.find("time", attrs={"datetime": True})
        value = t["datetime"] if t else ""
    if not value:
        for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
            m = re.search(r'"datePublished"\s*:\s*"([^"]+)"', tag.string or tag.get_text() or "")
            if m:
                value = m.group(1)
                break
    return parse_iso(value)


def _article_title(soup):
    title = _meta(soup, "og:title", "twitter:title")
    if not title:
        h1 = soup.find("h1")
        title = h1.get_text(" ") if h1 else (soup.title.get_text(" ") if soup.title else "")
    title = clean_text(title).replace("\n", " ")
    return re.sub(r"\s*[|\-–—]\s*NEMSU\s*$", "", title, flags=re.I).strip()


def parse_news_article(html, url):
    """One article page -> CollectedDoc (or None when it has no title)."""
    soup = BeautifulSoup(html, "html.parser")
    title = _article_title(soup)
    if not title:
        return None
    published = _published_from_page(soup)
    from_json = _article_from_page_json(soup)
    exact = _exact_article_from_page_json(soup)
    for tag in soup(_NOISE_TAGS):
        tag.decompose()
    box = soup.find("article") or soup.find("main") or soup.body or soup
    lines = clean_text(box.get_text("\n")).split("\n")

    author = None
    for i, line in enumerate(lines):                    # "by: Public Information Office | June 04, 2025"
        m = _BYLINE.match(line)
        if m:
            author = clean_text(m.group("author"))
            published = parse_date(m.group("date")) or published
            lines = lines[i + 1:]
            break

    for i, line in enumerate(lines):                    # the side list of OTHER articles starts here
        if _STOP.match(line) or _SIDE.match(line):
            cut = i
            if _SIDE.match(line):
                cut -= 1                                 # ...and the line above it is that article's title
                while cut >= 0 and not lines[cut]:
                    cut -= 1
            lines = lines[:max(cut, 0)]
            break

    norm_title = clean_text(title).lower()
    while lines and (not lines[0] or lines[0].lower() == norm_title
                     or (parse_date(lines[0]) and len(lines[0]) <= 20)):
        lines.pop(0)                                     # repeated title / lone date at the top
    content = clean_text("\n".join(lines))
    if from_json and len(from_json[0]) > len(content) + 40:     # the page is built by JavaScript
        content, author, published = from_json[0], author or from_json[1], published or from_json[2]
    if exact:                                                   # the site's own article field always wins
        content, author, published = exact[0], exact[1] or author, exact[2] or published
    return CollectedDoc(title=title, content=content, source_url=url,
                        published_at=published, source_type=NEWS, author=author)


def collect_news(fetcher, existing, pages, budget):
    base = config.NEMSU_NEWS_BASE
    stats = {"found": 0, "skipped_existing": 0, "errors": [], "method": None}
    seen, candidates, known = set(), [], set()

    def add(urls):
        for url in urls:
            if url in seen:
                continue
            seen.add(url)
            (known.add(url) if url in existing else candidates.append(url))

    # 1) the Newsroom list pages  /news, /news?page=2 ...
    for n in range(1, pages + 1):
        list_url = f"{base}/news" + ("" if n == 1 else f"?page={n}")
        try:
            response = fetcher.get(list_url)
        except (httpx.HTTPError, CollectorError) as exc:
            stats["errors"].append(f"{list_url}: {exc}")
            break
        urls = parse_news_list(response.text, list_url, base)
        if not urls:
            if n == 1:
                stats["errors"].append(_no_links_note(list_url, response))
            break
        add(urls)
        stats["method"] = "newsroom pages"
    # 2) the home page often shows the newest items too
    try:
        add(parse_news_list(fetcher.get(base + "/").text, base + "/", base))
    except (httpx.HTTPError, CollectorError):
        pass
    # 3) still nothing: ask the sitemap, then an RSS feed
    if not seen:
        for name, finder in (("sitemap.xml", _urls_from_sitemap), ("rss feed", _urls_from_feeds)):
            try:
                urls = finder(fetcher, base)
            except (httpx.HTTPError, CollectorError):
                urls = []
            if urls:
                add(urls[:pages * 20])
                stats["method"] = name
                break
    stats["found"] = len(seen)
    stats["skipped_existing"] = len(known)

    docs = []
    for url in candidates[:budget]:
        try:
            doc = parse_news_article(fetcher.get(url).text, url)
        except (httpx.HTTPError, CollectorError) as exc:
            stats["errors"].append(f"{url}: {exc}")
            continue
        if doc is None:
            stats["errors"].append(f"{url}: no title found (not an article?)")
            continue
        docs.append(doc)
    if len(candidates) > budget:
        stats["left_for_next_sync"] = len(candidates) - budget
    return docs, stats


# ------------------------------------------------------------------ source 2: Memorandums
def parse_wp_posts(posts, base):
    """WordPress REST API posts -> CollectedDoc list. A memo post is mostly a title + a
    Google Drive link, so the links are kept in the text."""
    docs = []
    for p in posts:
        link = p.get("link")
        title_html = (p.get("title") or {}).get("rendered") or ""
        title = clean_text(BeautifulSoup(title_html, "html.parser").get_text(" ")).replace("\n", " ")
        if not link or not title:
            continue
        body = BeautifulSoup((p.get("content") or {}).get("rendered") or "", "html.parser")
        links = [a["href"] for a in body.find_all("a", href=True)]
        text = clean_text(body.get_text("\n"))
        extra = [u for u in dict.fromkeys(links) if u not in text]
        if extra:
            text = (text + "\n\nDocument link: " + "\nDocument link: ".join(extra)).strip()
        docs.append(CollectedDoc(title=title, content=text,
                                 source_url=canonical_url(link, base),
                                 published_at=parse_iso(p.get("date")), source_type=MEMO,
                                 author="Records Unit"))
    return docs


def parse_memo_html(html, page_url, base):
    """Fallback when the JSON API is off: read the memo list on the home page."""
    soup = BeautifulSoup(html, "html.parser")
    docs, seen = [], set()
    for heading in soup.find_all(["h2", "h3"]):
        a = heading.find("a", href=True)
        if not a:
            continue
        url = canonical_url(a["href"], base, relative_to=page_url)
        path = urlsplit(url).path
        if (not _same_site(url, base) or path == "/" or url in seen
                or re.match(r"^/(category|author|tag|page|wp-|feed)", path)):
            continue
        title = clean_text(a.get_text(" ")).replace("\n", " ")
        node, date, text, links = heading, None, "", []
        for _ in range(5):                               # smallest wrapper holding ONE heading + a date
            node = node.parent
            if node is None or len(node.find_all(["h2", "h3"])) > 1:
                break
            text = node.get_text("\n")
            date = parse_date(text)
            if date:
                links = [x["href"] for x in node.find_all("a", href=True)
                         if "drive.google.com" in x["href"] or "docs.google.com" in x["href"]]
                links += re.findall(r"https?://(?:drive|docs)\.google\.com/\S+", text)
                break
        seen.add(url)
        content = "\n".join(f"Document link: {u}" for u in dict.fromkeys(links))
        if title:
            docs.append(CollectedDoc(title=title, content=content, source_url=url,
                                     published_at=date, source_type=MEMO, author="Records Unit"))
    return docs


def collect_memos(fetcher, existing, pages, budget):
    base = config.NEMSU_MEMO_BASE
    stats = {"found": 0, "skipped_existing": 0, "errors": []}
    fresh, known, seen = [], set(), set()

    def take(docs):
        for d in docs:
            if d.source_url in seen:
                continue
            seen.add(d.source_url)
            (known.add(d.source_url) if d.source_url in existing else fresh.append(d))

    try:
        for page in range(1, pages + 1):
            r = fetcher.get(f"{base}/wp-json/wp/v2/posts",
                            params={"per_page": 20, "page": page,
                                    "_fields": "id,date,link,title,content"})
            posts = r.json()
            if not isinstance(posts, list) or not posts:
                break
            take(parse_wp_posts(posts, base))
    except httpx.TransportError as exc:                  # timeout / cannot connect: the site itself is not answering
        stats["errors"].append(f"{base}: no answer from the memo website ({type(exc).__name__}). "
                               f"Check your internet or try again later.")
    except (httpx.HTTPError, CollectorError, ValueError) as exc:
        if not seen:                                     # the JSON API is not available -> read the page
            stats["errors"].append(f"{base}/wp-json: {exc} (reading the HTML page instead)")
            try:
                take(parse_memo_html(fetcher.get(base + "/").text, base + "/", base))
            except (httpx.HTTPError, CollectorError) as exc2:
                stats["errors"].append(f"{base}/: {exc2}")
        else:
            stats["errors"].append(f"{base}/wp-json: {exc}")
    stats["found"] = len(seen)
    stats["skipped_existing"] = len(known)
    if len(fresh) > budget:
        stats["left_for_next_sync"] = len(fresh) - budget
    return fresh[:budget], stats


# ------------------------------------------------------------------ saving + the sync
def _hash(doc):
    return hashlib.sha256(f"{doc.title}\n{doc.content}".encode("utf-8")).hexdigest()


def save_documents(db: Session, docs):
    """Insert the documents whose source_url is new. Returns how many were saved."""
    saved = 0
    for d in docs:
        row = KnowledgeDocument(
            title=d.title, content=d.content or d.title, source_url=d.source_url,
            published_at=d.published_at, source_type=d.source_type, author=d.author,
            content_hash=_hash(d))
        try:
            with db.begin_nested():                      # one bad row never loses the others
                db.add(row)
                db.flush()
            saved += 1
        except IntegrityError:
            pass                                          # someone saved the same URL first
    db.commit()
    return saved


SOURCES = (("nemsu_news", collect_news), ("nemsu_memo", collect_memos))


def sync(db, *, pages=None, dry_run=False, client=None, delay=None, sources=None):
    """Collect new public NEMSU documents. `db` may be None only for a dry run.

    Returns {"success", "new_documents", "skipped_existing", "errors", "sources", "new_items"}.
    """
    pages = max(1, min(int(pages or config.NEMSU_NEWS_PAGES), 30))
    wanted = {x.strip().lower() for x in (sources or config.NEMSU_SOURCES)}
    active = [(n, c) for n, c in SOURCES if n.replace("nemsu_", "") in wanted]
    if not active:
        raise CollectorError("No source selected. Use news, memo or news,memo.")
    existing = set(db.execute(select(KnowledgeDocument.source_url)).scalars()) if db is not None else set()
    fetcher = Fetcher(client=client, delay=delay)
    summary = {"success": True, "new_documents": 0, "skipped_existing": 0,
               "errors": [], "sources": {}, "new_items": []}
    budget = config.NEMSU_MAX_NEW_PER_SYNC
    failed = 0
    try:
        for name, collect in active:
            try:
                docs, stats = collect(fetcher, existing, pages, max(budget, 0))
            except Exception as exc:                      # one source down must not stop the other
                failed += 1
                summary["errors"].append(f"{name}: {exc!r}")
                summary["sources"][name] = {"new": 0, "error": repr(exc)}
                continue
            saved = len(docs) if dry_run else save_documents(db, docs)
            budget -= len(docs)
            summary["new_documents"] += saved
            summary["skipped_existing"] += stats["skipped_existing"]
            summary["errors"] += stats["errors"]
            summary["sources"][name] = {"new": saved, "found": stats["found"],
                                        "skipped_existing": stats["skipped_existing"],
                                        **({"method": stats["method"]} if stats.get("method") else {}),
                                        **({"left_for_next_sync": stats["left_for_next_sync"]}
                                           if "left_for_next_sync" in stats else {})}
            summary["new_items"] += [
                {"title": d.title, "source_type": d.source_type, "source_url": d.source_url,
                 "published_at": d.published_at.strftime("%Y-%m-%d") if d.published_at else None,
                 "content_chars": len(d.content)} for d in docs[:10]]
    finally:
        fetcher.close()
    found_any = summary["new_documents"] or summary["skipped_existing"]
    summary["success"] = not (failed == len(active) or (summary["errors"] and not found_any))
    if dry_run:
        summary["dry_run"] = True
    return summary