from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import orders, webhooks
from app.config import get_settings
from app.database import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.database_url.startswith("sqlite"):
        # Tự tạo bảng cho dev. Postgres dùng Alembic.
        await init_db()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Payment QR Backend",
        description="Tự động xác nhận thanh toán qua biến động số dư SMS từ ngân hàng VN.",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(orders.router)
    app.include_router(webhooks.router)

    @app.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

        @app.get("/", include_in_schema=False)
        async def index() -> FileResponse:
            return FileResponse(static_dir / "index.html")

        @app.get("/checkout/{order_code}", include_in_schema=False)
        async def checkout(order_code: str) -> FileResponse:
            return FileResponse(static_dir / "checkout.html")

    return app


app = create_app()
