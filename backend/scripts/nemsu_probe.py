"""
scripts/nemsu_probe.py - shows what the NEMSU websites really send to the collector.

Run from the backend/ folder:   python -m scripts.nemsu_probe
Copy the whole output if the collector finds nothing. It only READS public pages
(it opens each address once) and saves nothing.
"""

import html as html_lib
import json
import re
from urllib.parse import urljoin

import httpx

from app import config
from app.services.nemsu_collector import USER_AGENT

NEWS, MEMO = config.NEMSU_NEWS_BASE, config.NEMSU_MEMO_BASE
URLS = [NEWS + "/news", NEWS + "/news?page=2", NEWS + "/", NEWS + "/sitemap.xml", NEWS + "/robots.txt",
        MEMO + "/wp-json/wp/v2/posts?per_page=2&_fields=id,date,link,title", MEMO + "/"]
MARKERS = ["data-page=", "__NEXT_DATA__", "__NUXT__", 'id="app"', 'id="root"', "cf-chl",
           "challenge-platform", "Just a moment", "<article", "Read More"]


def probe(client, url):
    print("=" * 78)
    print(url)
    try:
        r = client.get(url)
    except httpx.HTTPError as exc:
        print("  FAILED:", type(exc).__name__, exc)
        return
    text = r.text or ""
    title = re.search(r"<title[^>]*>(.*?)</title>", text, re.S | re.I)
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', text)
    news_links = [h for h in dict.fromkeys(hrefs) if "/news/" in h]
    print(f"  HTTP {r.status_code}  final: {r.url}  type: {r.headers.get('content-type', '?')}")
    print(f"  server: {r.headers.get('server', '?')}  bytes: {len(text)}  <a> links: {len(hrefs)}")
    print("  <title>:", re.sub(r"\s+", " ", title.group(1)).strip()[:100] if title else "(none)")
    print("  markers:", [m for m in MARKERS if m in text] or "none")
    print(f"  links containing /news/: {len(news_links)}", news_links[:6])
    srcs = re.findall(r'<script[^>]+src=["\']([^"\']+)', text)
    print("  scripts:", srcs[:6])
    visible = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text, flags=re.S | re.I)
    visible = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", visible)).strip()
    print("  visible text starts:", visible[:200] or "(empty)")
    if url.rstrip("/") == NEWS + "/news":
        inspect_page_data(client, str(r.url), text)


def _short(value, n=90):
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    return text if len(text) <= n else text[:n] + "..."


def describe(obj, path="data-page", out=None, depth=0):
    """Outline of the page's JSON: keys, list sizes and one sample item per list."""
    out = [] if out is None else out
    if len(out) > 45 or depth > 6:
        return out
    if isinstance(obj, dict):
        out.append(f"  {path}: object with keys {list(obj)[:14]}")
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                describe(v, f"{path}.{k}", out, depth + 1)
    elif isinstance(obj, list):
        out.append(f"  {path}: list of {len(obj)}")
        if obj and isinstance(obj[0], dict):
            out.append("    first item: " + _short({k: _short(v, 60) for k, v in obj[0].items()}, 700))
        elif obj:
            describe(obj[0], path + "[0]", out, depth + 1)
    return out


def inspect_page_data(client, url, text):
    from bs4 import BeautifulSoup
    from app.services.nemsu_collector import _page_json
    data = _page_json(BeautifulSoup(text, "html.parser"))
    print("  --- DATA INSIDE THE PAGE (data-page) ---")
    if data is None:
        for m in re.finditer(r"<[^>]*data-page=[^>]*>", text):
            print("  a tag with data-page, but no readable JSON:", m.group(0)[:200])
        return
    print("  component:", data.get("component"), " url:", data.get("url"))
    for line in describe(data.get("props", {}), "props"):
        print(line)
    print("  --- ADDRESSES FOUND IN THE PAGE'S SCRIPT FILES ---")
    found = []
    for src in re.findall(r'<script[^>]+src=["\']([^"\']+)', text):
        if "/build/assets/" not in src:
            continue
        try:
            js = client.get(urljoin(url, src)).text
        except httpx.HTTPError:
            continue
        for pattern in (r"""["'`](/(?:api/)?[\w\-/{}$.]*(?:news|post|article|announcement)[\w\-/{}$.?=&]*)["'`]""",
                        r"""(?:axios|http|fetch)[\w.]*\(\s*["'`]([^"'`]+)["'`]"""):
            found += re.findall(pattern, js)
    for item in list(dict.fromkeys(found))[:25]:
        print("   ", item)
    if not found:
        print("    (none)")


def main():
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True,
                      transport=httpx.HTTPTransport(retries=2)) as client:
        for url in URLS:
            probe(client, url)


if __name__ == "__main__":
    main()