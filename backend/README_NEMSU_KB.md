# NEMSU Knowledge Base - Phase 1 (data collection)

Collects PUBLIC, official NEMSU announcements into the PostgreSQL table `knowledge_documents`.
No Facebook. No login. Nothing private.

## Files
| File | What it is |
|---|---|
| `app/models.py` | new table `KnowledgeDocument` (`knowledge_documents`, unique `source_url`). Created automatically at startup. |
| `app/services/nemsu_collector.py` | the collector: reads Newsroom posts, memos, and official pages; updates changed records |
| `app/routers/nemsu.py` | `POST /api/nemsu/sync`, `POST /api/nemsu/sync/scheduled`, `GET /api/nemsu/documents` |
| `scripts/nemsu_sync.py` | command line: `python -m scripts.nemsu_sync [--dry-run] [--pages N]` |
| `scripts/nemsu_probe.py` | shows what the NEMSU sites really send (use it when a sync finds nothing) |
| `app/config.py`, `app/main.py`, `requirements.txt` | settings, router registered, `beautifulsoup4` added |
| `tests/test_nemsu_collector.py` | offline tests (no internet needed) |

## Settings (.env / Render environment) - all optional
`NEMSU_NEWS_BASE`, `NEMSU_MEMO_BASE`, `NEMSU_NEWS_PAGES` (default 30), `NEMSU_MAX_NEW_PER_SYNC` (25),
`NEMSU_COLLECT_DELAY` (1.0 s), `NEMSU_COLLECT_TIMEOUT` (20 s), `NEMSU_SOURCES` (`news,memo` - set `news` if the memo site is down), `NEMSU_SYNC_TOKEN` (for schedulers; empty = off).

## First test on your own computer (from backend/)
1. `pip install -r requirements.txt`
2. `python -m scripts.nemsu_sync --dry-run` - reads the real sites, saves nothing, needs no database.
   You should see `new_documents` > 0 and a list of titles in `new_items`.
If it finds nothing, the `errors` list says why. Then run `python -m scripts.nemsu_probe` and read/send its output.
3. `python -m scripts.nemsu_sync --pages 10` - saves them (first run: also older news).
4. Run it again: `new_documents` must be 0 and `skipped_existing` > 0.
5. Check what was stored: sign in as admin, open `/api/nemsu/documents` (or `/api/docs`).

## Triggering from the API
* Admin signed in: `POST /api/nemsu/sync?pages=3` (add `&dry_run=true` to test). Needs the CSRF header like every admin call.
* With curl (development): set `NEMSU_SYNC_TOKEN=some-long-random-text` in .env, then
  `curl -X POST -H "X-Sync-Token: some-long-random-text" http://localhost:8000/api/nemsu/sync/scheduled`

## Automatic updates

The repository includes `.github/workflows/nemsu-sync.yml`, which calls the protected sync endpoint every three hours and can also be started with **Actions → Sync NEMSU public information → Run workflow**.

Configure these repository Actions secrets:

* `NEMSU_SYNC_URL`: the deployed backend URL ending in `/api/nemsu/sync/scheduled`.
* `NEMSU_SYNC_TOKEN`: the same long random value configured as `NEMSU_SYNC_TOKEN` in the backend environment.

The collector checks up to 30 Newsroom and memo list pages, plus the official pages listed in `app/services/official_pages.py`. It imports new posts in batches and refreshes known URLs; changed titles, contents, dates, or authors update the existing `knowledge_documents` row. The per-run new item limit is `NEMSU_MAX_NEW_PER_SYNC`; remaining new items are picked up by following scheduled runs. It only imports public pages and announcements. Changes to private or unlisted posts cannot be detected by these public sources.

## Later
* Phase 3 (RAG): chunk `content`, embed, vector search (pgvector), inject into the Hugging Face prompt, cite `source_url`.
* Facebook / PDFs: add a function that returns `CollectedDoc(... source_type="facebook")` and append it to `SOURCES`
  in `nemsu_collector.py`. The table needs no change.

## Official website pages (source `page`)

The chatbot also reads fixed pages of nemsu.edu.ph (leadership, colleges, research, campuses).
The list is `app/services/official_pages.py` - add a link there to teach the AI a new page.
Run a sync (`POST /api/nemsu/sync?sources=page`, add `&dry_run=true` to test without saving).
The scheduled sync rereads these pages and updates their existing records when their content changes.
`NEMSU_SOURCES` now defaults to `news,memo,page`.
