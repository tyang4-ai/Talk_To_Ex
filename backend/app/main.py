"""FastAPI entrypoint: lifespan creates tables, health route, router includes,
and (if built) serves the React SPA from frontend/dist."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
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
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend")
