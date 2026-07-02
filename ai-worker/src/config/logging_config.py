"""
Dual-output logging: human-readable console (as before) + rotating JSON
log files on disk, so logs survive container restarts/removal instead of
only existing in `docker compose logs` output.
"""
import logging
import logging.handlers
import os

import structlog

LOG_DIR = os.environ.get("LOG_DIR", "/app/logs")
LOG_FILE = "ai-worker.log"
MAX_BYTES = 10 * 1024 * 1024
BACKUP_COUNT = 5


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

    file_handler = logging.handlers.RotatingFileHandler(
        os.path.join(LOG_DIR, LOG_FILE), maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT,
    )
    file_handler.setFormatter(structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(),
        foreign_pre_chain=shared_processors,
    ))

    root_logger = logging.getLogger()
    root_logger.handlers = [console_handler, file_handler]
    root_logger.setLevel(logging.INFO)
