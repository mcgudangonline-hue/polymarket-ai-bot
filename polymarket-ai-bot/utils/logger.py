import logging
import os

LOG_DIR = "logs"
LOG_FILE = "bot.log"

def setup_logger():
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)

    log_path = os.path.join(LOG_DIR, LOG_FILE)

    logger = logging.getLogger("polymarket_bot")
    logger.setLevel(logging.INFO)

    file_handler = logging.FileHandler(log_path)
    console_handler = logging.StreamHandler()

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s"
    )

    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger