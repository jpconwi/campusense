"""Repair saved articles that contain broken characters (for example 'â€"' or 'ðTM...').

  python -m scripts.fix_encoding           # only reports what it would do
  python -m scripts.fix_encoding --apply   # saves the changes

* A row that can be repaired is repaired.
* A row that was damaged beyond repair (older syncs also turned the broken symbol into the
  letters 'TM') is DELETED, so the next `python -m scripts.nemsu_sync --sources news --pages 10`
  collects it again, correctly.
"""
import re
import sys

from sqlalchemy import select

from app.database import SessionLocal
from app.models import KnowledgeDocument
from app.services.nemsu_collector import fix_mojibake

STILL_BROKEN = re.compile("\u00f0(TM|[\u0080-\u00ff\u2122])|\u00e2\u20ac")


def main():
    apply = "--apply" in sys.argv
    repaired = deleted = 0
    with SessionLocal() as db:
        for doc in db.execute(select(KnowledgeDocument)).scalars():
            title, content = fix_mojibake(doc.title), fix_mojibake(doc.content)
            if STILL_BROKEN.search(title) or STILL_BROKEN.search(content):
                deleted += 1
                if apply:
                    db.delete(doc)
            elif (title, content) != (doc.title, doc.content):
                repaired += 1
                if apply:
                    doc.title, doc.content = title, content
        if apply:
            db.commit()
    verb = "" if apply else " (dry run; add --apply to save)"
    print(f"repaired: {repaired}, deleted so they can be collected again: {deleted}{verb}")


if __name__ == "__main__":
    main()