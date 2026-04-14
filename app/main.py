"""Thermal Printer Terminal — FastAPI application."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.db import init_db
from app.queue_worker import queue_worker_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Suppress httpx request logging — it includes full URLs with credentials
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

_worker_task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _worker_task
    await init_db()
    logger.info("Database initialized")
    _worker_task = asyncio.create_task(queue_worker_loop())
    logger.info("Queue worker started")
    yield
    if _worker_task:
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass
    logger.info("Queue worker stopped")


app = FastAPI(lifespan=lifespan)
from app.web import PREFIX  # noqa: E402

app.mount(f"{PREFIX}/static", StaticFiles(directory="app/static"), name="static")

# Import and include page routers
from app.pages import home, message, qso, emcomm, admin  # noqa: E402

app.include_router(home.router, prefix=PREFIX)
app.include_router(message.router, prefix=PREFIX)
app.include_router(qso.router, prefix=PREFIX)
app.include_router(emcomm.router, prefix=PREFIX)
app.include_router(admin.router, prefix=PREFIX)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8080,
        reload=False,
    )
