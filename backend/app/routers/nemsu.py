"""
routers/nemsu.py - the NEMSU knowledge base: sync the public announcements and look at them.

  POST /api/nemsu/sync              admin (signed in + CSRF) - run a sync now
        ?pages=3                    how many newsroom list pages to read (1-30)
        &dry_run=true               collect but do NOT save (to test the collector)
        &sources=page               only the official website pages (news, memo, page)
  POST /api/nemsu/sync/scheduled    for a scheduler. Needs the header  X-Sync-Token: <NEMSU_SYNC_TOKEN>
                                    from .env. Without NEMSU_SYNC_TOKEN set it is switched off (404).
  GET  /api/nemsu/documents         admin - the newest saved documents (to check the result)
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import KnowledgeDocument
from app.security import admin_required, csrf_protect

router = APIRouter(prefix="/api/nemsu", tags=["nemsu"])


@router.post("/sync", dependencies=[Depends(admin_required), Depends(csrf_protect)])
def sync_now(pages: int = Query(None, ge=1, le=30), dry_run: bool = False,
             sources: str = Query(None, description="e.g. page  or  news,memo,page"),
             db: Session = Depends(get_db)):
    raise HTTPException(410, "Website collection is disabled. Use the provided campus datasets.")


@router.post("/sync/scheduled")
def sync_scheduled():
    raise HTTPException(410, "Website collection is disabled.")


@router.get("/documents", dependencies=[Depends(admin_required)])
def documents(limit: int = Query(20, ge=1, le=100), source_type: str = None,
              db: Session = Depends(get_db)):
    query = select(KnowledgeDocument)
    count = select(func.count()).select_from(KnowledgeDocument)
    if source_type:
        query = query.where(KnowledgeDocument.source_type == source_type)
        count = count.where(KnowledgeDocument.source_type == source_type)
    rows = db.execute(query.order_by(KnowledgeDocument.published_at.desc().nullslast(),
                                     KnowledgeDocument.id.desc()).limit(limit)).scalars()
    return {"total": db.execute(count).scalar_one(), "rows": [{
        "id": r.id, "title": r.title, "source_type": r.source_type, "source_url": r.source_url,
        "published_at": r.published_at.strftime("%Y-%m-%d") if r.published_at else None,
        "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        "content_chars": len(r.content or ""),
        "content_preview": (r.content or "")[:300]} for r in rows]}
