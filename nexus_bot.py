"""NEXUS Telegram Bot — kjøres som egen tjeneste."""

import logging
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
Path("logs").mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/telegram.log", encoding="utf-8"),
    ],
)

from tools.telegram_bot import start_bot

if __name__ == "__main__":
    start_bot()
