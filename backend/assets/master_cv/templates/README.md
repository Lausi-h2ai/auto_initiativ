# Master CV template adapters

Templates are normalized at runtime by `backend/app/master_cv/templates.py`.
Only catalog IDs are accepted; upstream sample HTML is never served directly.
The renderer inserts validated structured content into an application-owned A4
shell and escapes every user-visible value.
