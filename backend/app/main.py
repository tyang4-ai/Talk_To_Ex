"""FastAPI entrypoint: lifespan creates tables, health route, router includes,
and (if built) serves the React SPA from frontend/dist."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import settings
from .db import init_db


class SPAStaticFiles(StaticFiles):
    """Static files with single-page-app fallback: any missing path that isn't an
    API/asset request serves index.html, so client-side routes (``/intake``,
    ``/dashboard`` …) work on deep-link and refresh, not just in-app navigation."""

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            req_path = scope.get("path", "") or ""
            if exc.status_code == 404 and not req_path.startswith("/api"):
                return await super().get_response("index.html", scope)
            raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Register the fine-tune job handler so a worker process can pick up jobs
    # (spec §23). The real training step is host-only; see ops/finetune/.
    if settings.finetune_enabled:
        try:
            from .finetune import pipeline

            pipeline.register_handler()
        except Exception as exc:  # noqa: BLE001 — never block startup on this
            logging.getLogger("talk_to_ex").warning(
                "finetune handler not registered: %s", exc
            )
    yield


app = FastAPI(title="Talk_To_Ex", lifespan=lifespan)


@app.get("/api/health")
def health():
    return {"ok": True}


def _include_routers() -> None:
    """Mount each router independently so one broken/not-yet-built module can't
    silently unmount the whole API. Import failures are logged, not swallowed."""
    import importlib

    specs = [
        ".auth.routes",
        ".billing.routes",
        ".billing.webhook",
        ".ingestion.routes",
        ".persona.routes",
        ".messaging.twilio_webhook",
    ]
    for mod_name in specs:
        try:
            mod = importlib.import_module(mod_name, package=__package__)
            app.include_router(mod.router)
        except Exception as exc:  # noqa: BLE001 — surface, don't hide, at bring-up
            logging.getLogger("talk_to_ex").warning(
                "router %s not mounted: %s", mod_name, exc
            )


_include_routers()

_frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/", SPAStaticFiles(directory=str(_frontend_dist), html=True), name="frontend")
