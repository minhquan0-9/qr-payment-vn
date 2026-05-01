"""Entry point cho container worker.

Chạy:
    BANK_TYPE=mb  python -m app.worker
    BANK_TYPE=acb python -m app.worker
    BANK_TYPE=tpb python -m app.worker

Mỗi container 1 worker / 1 NH. Tất cả worker đẩy giao dịch vào cùng DB và
publish event lên cùng event bus → web bán hàng nhận realtime "paid"
bất kể tiền vào từ NH nào.
"""
from __future__ import annotations

import asyncio
import logging
import signal
import sys

from app.config import get_settings
from app.database import init_db
from app.services.banking import build_client_from_settings
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

    try:
        client = build_client_from_settings(settings)
    except ValueError as exc:
        logger.error("Worker config error: %s", exc)
        sys.exit(1)

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
            pass

    logger.info("Worker started: bank_type=%s", settings.bank_type)
    await poller.run_forever()


if __name__ == "__main__":
    asyncio.run(main())
