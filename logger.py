import sys
import re
from pathlib import Path
from loguru import logger

from config import LOG_DIR, log as log_config

LOG_DIR.mkdir(exist_ok=True)


def setup_logger(name: str = __name__):
    logger.remove()

    logger.add(
        sys.stdout,
        format=log_config.format,
        level=log_config.level,
        colorize=True,
    )

    logger.add(
        LOG_DIR / "scraper_{time:YYYY-MM-DD}.log",
        format=log_config.format,
        level=log_config.level,
        rotation="1 day",
        retention="30 days",
        compression="gz",
        colorize=False,
    )

    logger.add(
        LOG_DIR / "error_{time:YYYY-MM-DD}.log",
        format=log_config.format,
        level="ERROR",
        rotation="1 day",
        retention="30 days",
        compression="gz",
        colorize=False,
        filter=lambda record: record["level"].name == "ERROR",
    )

    return logger


def log_step(step: str, message: str):
    logger.info(f"[{step}] {message}")


def log_product(product_url: str, message: str = ""):
    handle = product_url.split("/")[-1][:40]
    msg = f"[{handle}]" + (f" {message}" if message else "")
    logger.debug(msg)


def log_error(product_url: str, error: Exception):
    handle = product_url.split("/")[-1][:40] if product_url else "unknown"
    logger.error(f"[{handle}] {type(error).__name__}: {error}")


def log_batch_progress(current: int, total: int, batch_num: int):
    pct = (current / total * 100) if total > 0 else 0
    logger.info(f"Batch {batch_num} | Progress: {current}/{total} ({pct:.1f}%)")