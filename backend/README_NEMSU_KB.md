# NEMSU website knowledge collection (disabled)

The chatbot does not retrieve or answer from pages crawled from `nemsu.edu.ph` or other websites.
Website collection endpoints return HTTP 410, and website-derived rows that remain in
`knowledge_documents` are excluded from chatbot retrieval. They are retained only for admin
inspection; no database rows are deleted by this change.

NEMSU-specific answers use the supplied campus datasets, administrator announcements, and live
operational records. If those sources do not contain an answer, the chatbot says it cannot verify
the fact from the provided data instead of falling back to website or model-training knowledge.

## Relevant code

- `app/services/campus_service.py` reads the supplied campus information dataset and admin-edited
  campus records.
- `app/ai/context.py` adds supplied campus records and current admin announcements to prompts.
- `app/services/knowledge_service.py` keeps legacy website-document helpers, but its retrieval
  boundary returns no crawled website rows.
- `app/routers/nemsu.py` disables collection and exposes existing saved rows for admin inspection.

The old collector and sync scripts remain in the repository for reference, but chatbot answers do
not use their content. Re-enabling website collection or retrieval would violate the current
dataset-only grounding rule.
