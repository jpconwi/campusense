"""
services/chart_service.py - the numbers behind the admin dashboard charts.

Everything is a real count from the database. The React dashboard draws them
as plain inline SVG/CSS (no chart library needed). Only the admin dashboard
uses this file.
"""

import math
from datetime import datetime, timedelta

from sqlalchemy import Date, cast, func, select, union_all
from sqlalchemy.orm import Session

from app.models import Concern, Report
from app.services import faculty_service
from app.services.common import FEEDBACK_STATUSES, MODELS, WORKFLOW_STATUSES  # noqa: F401

STATUS_COLORS = {
    "Pending": "#f2b705", "Under Review": "#17119e", "In Progress": "#6f6cf0",
    "Resolved": "#2e9b57", "Rejected": "#b3121c", "Reviewed": "#2e9b57",
    "Approved": "#2e9b57", "Cancelled": "#8a8cab",
    "Absent": "#b3121c", "Available": "#2e9b57",
}
SERIES = [  # trend chart: (table, label, color)
    ("concerns", "Concerns", "#17119e"),
    ("reports", "Reports", "#f2b705"),
    ("feedback", "Feedback", "#2a9d8f"),
    ("reservations", "Reservations", "#8e44ad"),
]
# fixed names only - SQL is never built from user input
_GROUP_COLUMNS = {("concerns", "status"), ("reports", "status"),
                  ("concerns", "concern_type"), ("reports", "report_type")}


def _counts(db: Session, table, column):
    if (table, column) not in _GROUP_COLUMNS:
        raise ValueError("not allowed")
    col = getattr(MODELS[table], column)
    n = func.count().label("n")
    rows = db.execute(select(col, n).group_by(col).order_by(n.desc(), col)).all()
    return [(k or "(none)", c) for k, c in rows]


# ------------------------------------------------------------------ donut
def donut(title, pairs):
    """pairs = [(label, count), ...] -> segments for an SVG donut."""
    total = sum(n for _, n in pairs)
    segments, used = [], 0.0
    for label, n in pairs:
        if n <= 0:
            continue
        pct = n * 100.0 / total
        segments.append({"label": label, "count": n, "pct": round(pct),
                         "dash": round(pct, 2), "gap": round(100 - pct, 2),
                         "offset": round(25 - used, 2),
                         "color": STATUS_COLORS.get(label, "#8a8cab")})
        used += pct
    return {"title": title, "total": total, "segments": segments}


def by_status(db, table, order):
    found = dict(_counts(db, table, "status"))
    return donut(f"{table.title()} by status", [(s, found.get(s, 0)) for s in order])


# -------------------------------------------------------- horizontal bars
def hbars(pairs, limit=6, color="#17119e"):
    pairs = pairs[:limit]
    top = max([n for _, n in pairs], default=0) or 1
    return [{"label": k, "count": n, "width": max(3, round(n * 100 / top)), "color": color}
            for k, n in pairs]


def top_locations(db: Session, limit=6):
    both = union_all(select(Concern.location.label("location")),
                     select(Report.location.label("location"))).subquery()
    n = func.count().label("n")
    rows = db.execute(select(both.c.location, n).group_by(both.c.location)
                      .order_by(n.desc(), both.c.location).limit(limit)).all()
    return [(k, c) for k, c in rows]


# ------------------------------------------------------- 14-day trend (SVG)
def trend(db: Session, days=14):
    today = datetime.now().date()
    dates = [today - timedelta(days=i) for i in range(days - 1, -1, -1)]
    first = datetime.combine(dates[0], datetime.min.time())
    per_day = {d.strftime("%Y-%m-%d"): {} for d in dates}
    for table, _, _ in SERIES:
        model = MODELS[table]
        day = cast(model.created_at, Date).label("d")
        for d, n in db.execute(select(day, func.count()).where(model.created_at >= first)
                               .group_by(day)).all():
            key = d.strftime("%Y-%m-%d")
            if key in per_day:
                per_day[key][table] = n

    totals = [sum(per_day[d.strftime("%Y-%m-%d")].values()) for d in dates]
    ymax = max(4, int(math.ceil(max(totals) / 4.0) * 4))

    width, height, left, right, top, bottom = 640, 240, 36, 8, 12, 34
    plot_w, plot_h = width - left - right, height - top - bottom
    slot = plot_w / days
    bar_w = slot * 0.62
    rects, labels = [], []
    for i, d in enumerate(dates):
        key = d.strftime("%Y-%m-%d")
        x = left + i * slot + (slot - bar_w) / 2
        y = top + plot_h
        for table, name, color in SERIES:
            n = per_day[key].get(table, 0)
            if n:
                h = n * plot_h / ymax
                y -= h
                rects.append({"x": round(x, 1), "y": round(y, 1), "w": round(bar_w, 1),
                              "h": round(h, 1), "color": color,
                              "tip": f"{d.strftime('%b %d')}: {n} {name.lower()}"})
        if (days - 1 - i) % 2 == 0 or days <= 7:
            labels.append({"x": round(left + i * slot + slot / 2, 1),
                           "text": d.strftime("%m-%d")})
    grid = [{"y": round(top + plot_h - plot_h * k / 4, 1), "text": int(ymax * k / 4)}
            for k in range(5)]
    return {"width": width, "height": height, "left": left, "right": width - right,
            "label_y": height - 12, "rects": rects, "labels": labels, "grid": grid,
            "total": sum(totals), "days": days,
            "legend": [{"name": n, "color": c} for _, n, c in SERIES]}


# ---------------------------------------------------------- faculty table
def faculty_status(db: Session):
    counts = {}
    for record in faculty_service.load_records(db):
        status = (record.get("status") or "Unknown").strip() or "Unknown"
        counts[status] = counts.get(status, 0) + 1
    return donut("Faculty reports by status", sorted(counts.items(), key=lambda kv: -kv[1]))


# -------------------------------------------------------------- everything
def dashboard_charts(db: Session):
    return {
        "trend": trend(db),
        "concern_status": by_status(db, "concerns", WORKFLOW_STATUSES),
        "report_status": by_status(db, "reports", WORKFLOW_STATUSES),
        "faculty_status": faculty_status(db),
        "concern_types": hbars(_counts(db, "concerns", "concern_type"), color="#17119e"),
        "report_types": hbars(_counts(db, "reports", "report_type"), color="#d99a00"),
        "locations": hbars(top_locations(db), color="#2a9d8f"),
    }
