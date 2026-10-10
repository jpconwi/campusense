# NEMSU Knowledge Base - Phase 1 (data collection)

Collects PUBLIC, official NEMSU announcements into the PostgreSQL table `knowledge_documents`.
No Facebook. No login. Nothing private.

## Files
| File | What it is |
|---|---|
| `app/models.py` | new table `KnowledgeDocument` (`knowledge_documents`, unique `source_url`). Created automatically at startup. |
| `app/services/nemsu_collector.py` | the collector: reads the Newsroom and the Memo site, cleans text, saves only NEW URLs |
| `app/routers/nemsu.py` | `POST /api/nemsu/sync`, `POST /api/nemsu/sync/scheduled`, `GET /api/nemsu/documents` |
| `scripts/nemsu_sync.py` | command line: `python -m scripts.nemsu_sync [--dry-run] [--pages N]` |
| `scripts/nemsu_probe.py` | shows what the NEMSU sites really send (use it when a sync finds nothing) |
| `app/config.py`, `app/main.py`, `requirements.txt` | settings, router registered, `beautifulsoup4` added |
| `tests/test_nemsu_collector.py` | offline tests (no internet needed) |

## Settings (.env / Render environment) - all optional
`NEMSU_NEWS_BASE`, `NEMSU_MEMO_BASE`, `NEMSU_NEWS_PAGES` (default 3), `NEMSU_MAX_NEW_PER_SYNC` (25),
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

## Phase 2 - run automatically on Render (prepared, not switched on)
Do not loop inside the web service (the free plan sleeps and 2 workers would both run it). Use one of:
* **Render Cron Job** (best): Command `python -m scripts.nemsu_sync`, schedule `0 */3 * * *` (every 3 hours),
  same environment variables as the web service (DATABASE_URL).
* **External scheduler** (cron-job.org, GitHub Actions): `POST https://<your-backend>/api/nemsu/sync/scheduled`
  with header `X-Sync-Token`.

## Later
* Phase 3 (RAG): chunk `content`, embed, vector search (pgvector), inject into the Hugging Face prompt, cite `source_url`.
* Facebook / PDFs: add a function that returns `CollectedDoc(... source_type="facebook")` and append it to `SOURCES`
  in `nemsu_collector.py`. The table needs no change.

## Official website pages (source `page`)

The chatbot also reads fixed pages of nemsu.edu.ph (leadership, colleges, research, campuses).
The list is `app/services/official_pages.py` - add a link there to teach the AI a new page.
Run a sync (`POST /api/nemsu/sync?sources=page`, add `&dry_run=true` to test without saving).
Pages are saved once; to re-read a changed page, delete its row in `knowledge_documents`.
`NEMSU_SOURCES` now defaults to `news,memo,page`.