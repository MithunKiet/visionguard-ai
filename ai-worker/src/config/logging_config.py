"""
Dual-output logging: human-readable console (as before) + rotating JSON
log files on disk, so logs survive container restarts/removal instead of
only existing in `docker compose logs` output.
"""
import logging
import logging.handlers
import os
from datetime import datetime

import structlog

LOG_DIR = os.environ.get("LOG_DIR", "/app/logs")
BACKUP_DAYS = 30


def _dated_namer(default_name: str) -> str:
    """TimedRotatingFileHandler default names rollovers like
    'YYYYMMDD.log.2026-07-03' — rewrite to '20260703.log' so every day's
    file, past or present, follows the same YYYYMMDD.log pattern."""
    base, _, date_suffix = default_name.rpartition(".")
    return os.path.join(LOG_DIR, f"{date_suffix.replace('-', '')}.log")


def configure_logging() -> None:
    os.makedirs(LOG_DIR, exist_ok=True)

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    structlog.configure(
        processors=shared_processors + [structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(structlog.stdlib.ProcessorFormatter(
        processor=structlog.dev.ConsoleRenderer(colors=True),
        foreign_pre_chain=shared_processors,
    ))

    log_file = os.path.join(LOG_DIR, datetime.now().strftime("%Y%m%d.log"))
    file_handler = logging.handlers.TimedRotatingFileHandler(
        log_file, when="midnight", backupCount=BACKUP_DAYS, encoding="utf-8",
    )
    file_handler.suffix = "%Y-%m-%d"
    file_handler.namer = _dated_namer
    file_handler.setFormatter(structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(),
        foreign_pre_chain=shared_processors,
    ))

    root_logger = logging.getLogger()
    root_logger.handlers = [console_handler, file_handler]
    root_logger.setLevel(logging.INFO)
