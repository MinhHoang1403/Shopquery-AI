"""Create the database schema and reader grants."""

import argparse

from app.database.session import get_setup_engine
from app.database.setup import create_schema

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Explicit schema expansion; no ownership backfill")
    parser.add_argument("--confirm-database", required=True)
    args = parser.parse_args()
    engine = get_setup_engine()
    if args.confirm_database != engine.url.database:
        parser.error("Database confirmation does not match the configured target")
    create_schema(engine)
    print("Schema expanded. Legacy ownership requires the separate explicit migration.")
