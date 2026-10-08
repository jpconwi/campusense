"""Offline tests for the NEMSU collector: no internet, SQLite in memory, fake web pages."""

import json

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models import KnowledgeDocument
from app.services import nemsu_collector as nc

NEWS = "https://nemsu.edu.ph"
MEMO = "https://memo.nemsu.edu.ph"

LIST_PAGE_1 = """<html><body><header><nav><a href="/">Home</a><a href="/news">News</a></nav></header>
<div class="card"><h3><a href="/news/PESOMAP-2024">𝐍𝐄𝐌𝐒𝐔 𝐇𝐨𝐬𝐭𝐬 𝐏𝐄𝐒𝐎𝐌𝐀𝐏 𝐒𝐮𝐫𝐢𝐠𝐚𝐨 𝐝𝐞𝐥 𝐒𝐮𝐫 𝐌𝐞𝐞𝐭𝐢𝐧𝐠</a></h3>
<p>by: Public Information Office | April 26, 2024</p><a href="/news/PESOMAP-2024">Read More</a></div>
<div class="card"><h3><a href="https://www.nemsu.edu.ph/index.php/news/Information-Unit-hosts-the-NEMSULTI">NEMSULTI</a></h3>
<a href="https://www.nemsu.edu.ph/index.php/news/Information-Unit-hosts-the-NEMSULTI/">Read More</a></div>
<a href="/news?page=2">2</a><a href="/about">About</a><a href="https://facebook.com/nemsu">fb</a></body></html>"""

ARTICLE_PESO = """<html><head><title>NEMSU Hosts PESOMAP | NEMSU</title>
<meta property="og:title" content="𝐍𝐄𝐌𝐒𝐔 𝐇𝐨𝐬𝐭𝐬 𝐏𝐄𝐒𝐎𝐌𝐀𝐏 𝐒𝐮𝐫𝐢𝐠𝐚𝐨 𝐝𝐞𝐥 𝐒𝐮𝐫 𝐌𝐞𝐞𝐭𝐢𝐧𝐠"></head><body>
<header><nav>Home News About</nav></header><main>
<h1>𝐍𝐄𝐌𝐒𝐔 𝐇𝐨𝐬𝐭𝐬 𝐏𝐄𝐒𝐎𝐌𝐀𝐏 𝐒𝐮𝐫𝐢𝐠𝐚𝐨 𝐝𝐞𝐥 𝐒𝐮𝐫 𝐌𝐞𝐞𝐭𝐢𝐧𝐠</h1>
<div>by: Public Information Office | April 26, 2024</div>
<p>NEMSU serves as the venue for the gathering of PESO managers in Surigao del Sur.</p>
<p>The ongoing event is held at NEMSU's campus in Tandag.</p>
<section><h4>THEY HAVE CONQUERED THE BAR EXAMS!</h4><div>Public Information Office | September 15, 2025</div>
<h4>Training on Thesis Advising</h4><div>Public Information Office | September 06, 2025</div></section>
</main><footer>© NEMSU</footer></body></html>"""

ARTICLE_UNIT = """<html><head><meta property="og:title" content="The NEMSU Information Unit hosts the NEMSULTI"></head>
<body><main><h1>The NEMSU Information Unit hosts the NEMSULTI</h1>
<div>by: Public Information Office | June 04, 2025</div>
<p>The 5th Executive Press Conference was held at NEMSU Tagbina Campus on June 2.</p>
<a href="/news/other">Read More</a></main></body></html>"""

WP_POSTS = [
    {"id": 1, "date": "2026-09-11T09:30:00", "link": MEMO + "/memo-no-0286-s-2026-packaging/",
     "title": {"rendered": "Memo No. 0286, s. 2026 PACKAGING OF THE SUMMARY REPORT &#8211; FUNDRAISING"},
     "content": {"rendered": "<p>https://drive.google.com/file/d/ABC/view?usp=sharing</p>"}},
    {"id": 2, "date": "2026-09-10T08:00:00", "link": MEMO + "/memo-no-0284-s-2026-nomination/",
     "title": {"rendered": "Memo No. 0284, s. 2026 NOMINATION"},
     "content": {"rendered": '<p><a href="https://drive.google.com/file/d/XYZ/view">Download</a></p>'}},
]

MEMO_HTML = """<html><body><div class="grid">
<article><a href="/category/memo/">Memo</a><a href="/x/">September 11, 2026</a>
<h3><a href="/memo-no-0286-s-2026-packaging/">Memo No. 0286, s. 2026 PACKAGING</a></h3>
<p>https://drive.google.com/file/d/ABC/view?usp=sharing</p></article>
<article><a href="/category/memo/">Memo</a><a href="/y/">September 10, 2026</a>
<h3><a href="/memo-no-0284-s-2026-nomination/">Memo No. 0284, s. 2026 NOMINATION</a></h3></article>
</div></body></html>"""


def make_client(fail=(), wp_json=True, robots="User-agent: *\nAllow: /"):
    def handler(request: httpx.Request):
        url = str(request.url)
        path = request.url.path
        if path == "/robots.txt":
            return httpx.Response(200, text=robots)
        if any(f in url for f in fail):
            return httpx.Response(500, text="boom")
        host = request.url.host
        if host == "nemsu.edu.ph":
            if path == "/news" and request.url.params.get("page") in (None, "1"):
                return httpx.Response(200, text=LIST_PAGE_1)
            if path == "/news":
                return httpx.Response(200, text="<html><body>no more</body></html>")
            if path == "/":
                return httpx.Response(200, text="<html><body><a href='/news/PESOMAP-2024'>x</a></body></html>")
            if path == "/news/PESOMAP-2024":
                return httpx.Response(200, text=ARTICLE_PESO)
            if path == "/news/Information-Unit-hosts-the-NEMSULTI":
                return httpx.Response(200, text=ARTICLE_UNIT)
        if host == "memo.nemsu.edu.ph":
            if path == "/wp-json/wp/v2/posts":
                if not wp_json:
                    return httpx.Response(404, json={"code": "rest_no_route"})
                page = request.url.params.get("page", "1")
                return httpx.Response(200, json=WP_POSTS if page == "1" else [])
            if path == "/":
                return httpx.Response(200, text=MEMO_HTML)
        return httpx.Response(404, text="not found")
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    KnowledgeDocument.__table__.create(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        yield session


def test_list_page_gives_clean_unique_article_urls():
    urls = nc.parse_news_list(LIST_PAGE_1, NEWS + "/news", NEWS)
    assert urls == [NEWS + "/news/PESOMAP-2024",
                    NEWS + "/news/Information-Unit-hosts-the-NEMSULTI"]   # www/index.php/slash variants merged


def test_article_is_cleaned():
    doc = nc.parse_news_article(ARTICLE_PESO, NEWS + "/news/PESOMAP-2024")
    assert doc.title == "NEMSU Hosts PESOMAP Surigao del Sur Meeting"      # fancy letters -> normal
    assert doc.author == "Public Information Office"
    assert doc.published_at.strftime("%Y-%m-%d") == "2024-04-26"
    assert "PESO managers in Surigao del Sur" in doc.content
    assert "BAR EXAMS" not in doc.content and "Home" not in doc.content    # sidebar + menu removed
    assert doc.content.startswith("NEMSU serves as the venue")             # title/byline not repeated


def test_memo_posts_from_the_wordpress_api():
    docs = nc.parse_wp_posts(WP_POSTS, MEMO)
    assert docs[0].title == "Memo No. 0286, s. 2026 PACKAGING OF THE SUMMARY REPORT – FUNDRAISING"
    assert "https://drive.google.com/file/d/ABC/view" in docs[0].content
    assert "https://drive.google.com/file/d/XYZ/view" in docs[1].content   # link kept even though the text was "Download"
    assert docs[0].published_at.strftime("%Y-%m-%d") == "2026-09-11"
    assert docs[0].source_url == MEMO + "/memo-no-0286-s-2026-packaging"


def test_memo_html_fallback():
    docs = nc.parse_memo_html(MEMO_HTML, MEMO + "/", MEMO)
    assert [d.published_at.strftime("%Y-%m-%d") for d in docs] == ["2026-09-11", "2026-09-10"]
    assert "drive.google.com/file/d/ABC" in docs[0].content


def test_sync_saves_new_and_skips_existing(db):
    first = nc.sync(db, client=make_client(), delay=0)
    assert first["success"] and first["new_documents"] == 4 and first["skipped_existing"] == 0
    rows = db.execute(select(KnowledgeDocument)).scalars().all()
    assert {r.source_type for r in rows} == {"nemsu_news", "nemsu_memo"} and len(rows) == 4
    second = nc.sync(db, client=make_client(), delay=0)
    assert second["new_documents"] == 0 and second["skipped_existing"] == 4
    assert db.execute(select(KnowledgeDocument)).scalars().all().__len__() == 4


def test_dry_run_saves_nothing(db):
    result = nc.sync(db, dry_run=True, client=make_client(), delay=0)
    assert result["new_documents"] == 4 and result["dry_run"]
    assert db.execute(select(KnowledgeDocument)).first() is None
    assert nc.sync(None, dry_run=True, client=make_client(), delay=0)["new_documents"] == 4   # no database needed


def test_memo_falls_back_to_html_when_api_is_off(db):
    result = nc.sync(db, client=make_client(wp_json=False), delay=0)
    assert result["sources"]["nemsu_memo"]["new"] == 2
    assert any("HTML page instead" in e for e in result["errors"])


def test_one_broken_article_does_not_stop_the_sync(db):
    result = nc.sync(db, client=make_client(fail=("PESOMAP-2024",)), delay=0)
    assert result["new_documents"] == 3
    assert any("PESOMAP-2024" in e for e in result["errors"])


def test_robots_txt_is_obeyed(db):
    result = nc.sync(db, client=make_client(robots="User-agent: *\nDisallow: /"), delay=0)
    assert result["new_documents"] == 0 and not result["success"]
    assert db.execute(select(KnowledgeDocument)).first() is None


# ---------------------------------------------------------------- pages built by JavaScript / other ways in
def _site(handlers):
    """Fake NEMSU site: handlers = {path: html or Response}. Memo site answers with the normal fixtures."""
    base = make_client()

    def handler(request: httpx.Request):
        if request.url.host == "nemsu.edu.ph" and request.url.path in handlers:
            h = handlers[request.url.path]
            return h if isinstance(h, httpx.Response) else httpx.Response(200, text=h)
        if request.url.host == "nemsu.edu.ph" and request.url.path != "/robots.txt":
            return httpx.Response(404, text="nope")
        return base.send(httpx.Request(request.method, request.url))
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


JS_SHELL = ("<html><body><div id=\"app\" data-page='" + json.dumps({"component": "News/Index", "props": {
    "news": {"data": [{"title": "Hello World", "slug": "Hello-World", "published_at": "2026-09-01"}]}}}) +
    "'></div><script src='/build/app.js'></script></body></html>")

JS_ARTICLE = ("<html><head><meta property='og:title' content='Hello World'></head><body><div id=\"app\" data-page='" +
              json.dumps({"props": {"news": {"title": "Hello World", "slug": "Hello-World",
                          "content": "<p>The full body of the article that only exists in the page data, not in visible text.</p>",
                          "published_at": "2026-09-01T08:00:00+08:00", "author": {"name": "Public Information Office"}}}}) +
              "'></div></body></html>")


def test_javascript_page_with_json_data_is_still_read(db):
    client = _site({"/news": JS_SHELL, "/news/Hello-World": JS_ARTICLE, "/": "<html></html>"})
    result = nc.sync(db, client=client, delay=0)
    assert result["sources"]["nemsu_news"]["new"] == 1
    row = db.execute(select(KnowledgeDocument).where(KnowledgeDocument.source_type == "nemsu_news")).scalar_one()
    assert row.source_url == NEWS + "/news/Hello-World" and "full body of the article" in row.content
    assert row.author == "Public Information Office" and row.published_at.strftime("%Y-%m-%d") == "2026-09-01"


def test_links_hidden_inside_scripts_are_found():
    html = "<html><script>window.__DATA__ = {\"items\":[{\"url\":\"https:\\/\\/nemsu.edu.ph\\/news\\/Some-Story\"}]}</script></html>"
    assert nc.parse_news_list(html, NEWS + "/news", NEWS) == [NEWS + "/news/Some-Story"]


def test_sitemap_is_used_when_the_list_page_has_no_links(db):
    sitemap = ("<urlset><url><loc>https://nemsu.edu.ph/news/Old-One</loc><lastmod>2024-01-01</lastmod></url>"
               "<url><loc>https://nemsu.edu.ph/news/Hello-World</loc><lastmod>2026-09-01</lastmod></url>"
               "<url><loc>https://nemsu.edu.ph/about</loc></url></urlset>")
    client = _site({"/news": "<html><body>empty shell</body></html>", "/sitemap.xml": sitemap,
                    "/news/Hello-World": JS_ARTICLE, "/news/Old-One": JS_ARTICLE})
    result = nc.sync(db, client=client, delay=0)
    assert result["sources"]["nemsu_news"]["method"] == "sitemap.xml"
    assert result["sources"]["nemsu_news"]["new"] == 2


def test_empty_list_page_explains_itself(db):
    result = nc.sync(db, client=_site({"/news": JS_SHELL.replace("Hello-World", "")}), delay=0)
    note = next(e for e in result["errors"] if "no article links" in e)
    assert "built by JavaScript" in note and "nemsu_probe" in note


def test_memo_site_not_answering_is_reported_once_and_fast(db):
    def handler(request: httpx.Request):
        if request.url.host == "memo.nemsu.edu.ph" and request.url.path != "/robots.txt":
            raise httpx.ConnectTimeout("timed out")
        return make_client().send(httpx.Request("GET", request.url))
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    result = nc.sync(db, client=client, delay=0)
    assert result["sources"]["nemsu_news"]["new"] == 2
    assert sum("no answer from the memo website" in e for e in result["errors"]) == 1


def test_a_source_can_be_switched_off(db):
    result = nc.sync(db, client=make_client(), delay=0, sources=["news"])
    assert result["new_documents"] == 2 and list(result["sources"]) == ["nemsu_news"]
    with pytest.raises(nc.CollectorError):
        nc.sync(db, client=make_client(), delay=0, sources=["facebook"])


def test_other_json_key_names_are_understood():
    for item in ({"headline": "Hi", "url": "https://www.nemsu.edu.ph/index.php/news/Hi-There"},
                 {"name": "Hi", "news_slug": "Hi-There"},
                 {"title": "Hi", "route": "/news/Hi-There"}):
        html = "<div id='app' data-page='" + json.dumps({"props": {"items": [item]}}) + "'></div>"
        assert nc.parse_news_list(html, NEWS + "/news", NEWS) == [NEWS + "/news/Hi-There"]


def test_inertia_data_inside_a_script_tag_is_read():
    """Newer Inertia sites: <script data-page="app" type="application/json">{...}</script>"""
    data = {"component": "News/Index", "props": {"news": {"data": [
        {"id": 1, "title": "Hello", "slug": "Hello-There"}, {"id": 2, "title": "Hi", "slug": "Hi-There"}]}}}
    html = ('<html><head></head><body><script data-page="app" type="application/json">' + json.dumps(data) +
            '</script><div id="app"></div></body></html>')
    assert nc.parse_news_list(html, NEWS + "/news", NEWS) == [NEWS + "/news/Hello-There", NEWS + "/news/Hi-There"]
    # and an article page whose text only exists in that data
    art = {"component": "News/Show", "props": {"news": {"title": "Hello", "slug": "Hello-There",
           "content": "<p>Body of the article that is only in the data.</p>", "published_at": "2026-10-01"}}}
    page = ('<html><head><meta property="og:title" content="Hello"></head><body><script data-page="app" '
            'type="application/json">' + json.dumps(art) + '</script><div id="app"></div></body></html>')
    doc = nc.parse_news_article(page, NEWS + "/news/Hello-There")
    assert "Body of the article" in doc.content and doc.published_at.strftime("%Y-%m-%d") == "2026-10-01"