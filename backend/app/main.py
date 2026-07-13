from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.auth.middleware import AuthWorkspaceMiddleware
from backend.app.auth.routes import router as auth_router
from backend.app.api.routes import router
from backend.app.db.session import init_db
from backend.app.core.config import get_settings
from backend.app.workflow.engine import start_workflow_worker, stop_workflow_worker
from backend.app.product.routes import router as product_router
from backend.app.monitoring.issues import IssueCaptureMiddleware, router as monitoring_router

STATIC_DIR = Path(__file__).parent / "static"
DESIGN_LAB_DIR = STATIC_DIR / "design-lab"
SPA_INDEX = STATIC_DIR / "app" / "index.html"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db()
    settings = get_settings()
    if settings.workflow_worker_enabled:
        start_workflow_worker(settings)
    try:
        yield
    finally:
        if settings.workflow_worker_enabled:
            stop_workflow_worker()


def create_app() -> FastAPI:
    app = FastAPI(title="Auto Initiativ Backend", version="0.1.0", lifespan=lifespan)
    app.add_middleware(AuthWorkspaceMiddleware)
    app.add_middleware(IssueCaptureMiddleware)
    app.include_router(auth_router)
    app.include_router(product_router)
    app.include_router(monitoring_router)
    app.include_router(router)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/dashboard", include_in_schema=False)
    def dashboard() -> FileResponse:
        return FileResponse(
            SPA_INDEX if SPA_INDEX.exists() else STATIC_DIR / "dashboard.html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    @app.get("/login", include_in_schema=False)
    def login() -> FileResponse:
        return FileResponse(
            SPA_INDEX if SPA_INDEX.exists() else STATIC_DIR / "dashboard.html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    @app.get("/register", include_in_schema=False)
    def register() -> FileResponse:
        return FileResponse(
            SPA_INDEX if SPA_INDEX.exists() else STATIC_DIR / "dashboard.html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    @app.get("/design-lab/concept-a", include_in_schema=False)
    def design_lab_concept_a() -> FileResponse:
        return FileResponse(DESIGN_LAB_DIR / "concept-a.html")

    @app.get("/design-lab/concept-b", include_in_schema=False)
    def design_lab_concept_b() -> FileResponse:
        return FileResponse(DESIGN_LAB_DIR / "concept-b.html")

    @app.get("/design-lab/concept-c", include_in_schema=False)
    def design_lab_concept_c() -> FileResponse:
        return FileResponse(DESIGN_LAB_DIR / "concept-c.html")

    return app


app = create_app()
