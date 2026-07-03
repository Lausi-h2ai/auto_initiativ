from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.api.routes import router
from backend.app.db.session import init_db

STATIC_DIR = Path(__file__).parent / "static"
DESIGN_LAB_DIR = STATIC_DIR / "design-lab"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Auto Initiativ Backend", version="0.1.0", lifespan=lifespan)
    app.include_router(router)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/dashboard", include_in_schema=False)
    def dashboard() -> FileResponse:
        return FileResponse(
            STATIC_DIR / "dashboard.html",
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
