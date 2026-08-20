import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from app.config import settings


def setup_logging():
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    os.makedirs(os.path.dirname(settings.LOG_FILE) or '.', exist_ok=True)
    try:
        file_handler = RotatingFileHandler(
            settings.LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    except Exception:
        pass

    for lib in ['httpx', 'urllib3', 'jose', 'passlib']:
        logging.getLogger(lib).setLevel(logging.WARNING)

    return root_logger


logger = setup_logging()
