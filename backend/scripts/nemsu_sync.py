"""
scripts/nemsu_sync.py - collect the newest public NEMSU announcements (news + memos).

Run from the backend/ folder:
    python -m scripts.nemsu_sync --dry-run          # look only: needs NO database, saves nothing
    python -m scripts.nemsu_sync                    # collect and save to PostgreSQL
    python -m scripts.nemsu_sync --pages 15         # first run: also read older newsroom pages
    python -m scripts.nemsu_sync --sources news     # newsroom only (use this if the memo site is down)

This same command is what a Render "Cron Job" runs on a schedule (see README_NEMSU_KB.md).
"""

import argparse
import json

from app.services import nemsu_collector


def main():
    parser = argparse.ArgumentParser(description="Collect public NEMSU announcements.")
    parser.add_argument("--pages", type=int, default=None, help="newsroom list pages to read (1-30)")
    parser.add_argument("--sources", default=None,
                        help="news, memo or news,memo (default: NEMSU_SOURCES in .env)")
    parser.add_argument("--dry-run", action="store_true", help="collect but do not save anything")
    args = parser.parse_args()

    if args.dry_run:
        result = nemsu_collector.sync(None, pages=args.pages, dry_run=True,
                                      sources=args.sources and args.sources.split(","))
    else:
        from app.database import SessionLocal, init_db
        init_db()
        with SessionLocal() as db:
            result = nemsu_collector.sync(db, pages=args.pages,
                                          sources=args.sources and args.sources.split(","))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    raise SystemExit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
