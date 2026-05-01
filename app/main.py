from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import bank, orders, webhooks
from app.config import get_settings
from app.database import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger("payment.app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.database_url.startswith("sqlite"):
        await init_db()

    poller_task: asyncio.Task | None = None
    if settings.enable_in_process_poller:
        from app.services.banking import build_client_from_settings
        from app.services.poller import BankPoller

        try:
            client = build_client_from_settings(settings)
            poller = BankPoller(
                client=client,
                interval_seconds=settings.poll_interval_seconds,
                lookback_minutes=settings.poll_lookback_minutes,
            )
            poller_task = asyncio.create_task(poller.run_forever())
            logger.info("In-process poller started: bank_type=%s", settings.bank_type)
        except ValueError as exc:
            logger.warning("In-process poller disabled: %s", exc)

    try:
        yield
    finally:
        if poller_task is not None:
            poller_task.cancel()
            try:
                await poller_task
            except (asyncio.CancelledError, Exception):
                pass


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Payment QR Backend",
        description=(
            "Backend tự động xác nhận thanh toán cho web bán hàng VN. "
            "Nguồn dữ liệu chính: MB Bank private API (worker poll). "
            "Tuỳ chọn fallback: webhook SMS từ Android forwarder."
        ),
        version="0.2.0",
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
    app.include_router(bank.router)
    if settings.enable_sms_webhook:
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
