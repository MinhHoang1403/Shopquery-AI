"""Load generated CSV files into PostgreSQL."""

from app.core.config import get_settings
from app.database.loader import load_seed_csv
from app.database.session import get_setup_engine

if __name__ == "__main__":
    settings = get_settings()
    counts = load_seed_csv(get_setup_engine(), settings.seed_directory)
    print(f"Loaded seed data: {counts}")
