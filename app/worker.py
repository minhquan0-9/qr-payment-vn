"""Entry point cho container worker (poll MB Bank).

Chạy độc lập với FastAPI app:
    python -m app.worker

Đọc config từ env (DATABASE_URL, MB_USERNAME, MB_PASSWORD, ...). Tự tạo bảng DB
nếu dùng SQLite; với Postgres giả định Alembic đã migrate.
"""

from __future__ import annotations

import asyncio
import logging
import signal

from app.config import get_settings
from app.database import init_db
from app.services.banking import MBBankClient
from app.services.poller import BankPoller

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger("payment.worker")


async def main() -> None:
    settings = get_settings()
    if settings.database_url.startswith("sqlite"):
        await init_db()

    if not settings.mb_username or not settings.mb_password:
        logger.error("MB_USERNAME / MB_PASSWORD chưa được cấu hình; worker exit.")
        return

    client = MBBankClient(
        username=settings.mb_username,
        password=settings.mb_password,
        account_no=settings.mb_account_no,
    )
    poller = BankPoller(
        client=client,
        interval_seconds=settings.poll_interval_seconds,
        lookback_minutes=settings.poll_lookback_minutes,
    )

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda: asyncio.create_task(poller.stop()))
        except NotImplementedError:
            # Windows / non-main thread không hỗ trợ
            pass

    await poller.run_forever()


if __name__ == "__main__":
    asyncio.run(main())
