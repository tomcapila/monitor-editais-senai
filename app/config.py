from pathlib import Path

import yaml
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "editais.db"
STATIC_DIR = BASE_DIR / "static"

load_dotenv(BASE_DIR / ".env")


def carregar_config() -> dict:
    with open(BASE_DIR / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)
