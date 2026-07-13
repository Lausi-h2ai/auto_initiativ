# Frontend Instructions

- Edit source in `frontend/src/`; do not hand-edit hashed files in `backend/app/static/app/assets/`.
- Run `npm run typecheck` after TypeScript changes.
- Run `npm run build` when the backend-served frontend assets must be updated.
- After rebuilding served assets or changing runtime behavior, restart the FastAPI app and verify `/health` and `/dashboard` as required by the root instructions.
