"""Repair already-saved articles that contain broken characters such as 'â€“'.

Run once (it only changes rows that need it):
    python -m scripts.fix_encoding          # shows how many rows would change
    python -m scripts.fix_encoding --apply  # saves the repairs
"""
import sys

from sqlalchemy import select

from app.database import SessionLocal
from app.models import KnowledgeDocument
from app.services.nemsu_collector import fix_mojibake


def main():
    apply = "--apply" in sys.argv
    changed = 0
    with SessionLocal() as db:
        for doc in db.execute(select(KnowledgeDocument)).scalars():
            title, content = fix_mojibake(doc.title), fix_mojibake(doc.content)
            if (title, content) != (doc.title, doc.content):
                changed += 1
                if apply:
                    doc.title, doc.content = title, content
        if apply:
            db.commit()
    print(f"{changed} row(s) {'repaired' if apply else 'would be repaired (add --apply to save)'}")


if __name__ == "__main__":
    main()