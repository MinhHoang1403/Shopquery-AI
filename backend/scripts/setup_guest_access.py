"""Configure the restricted TEMP role on an explicitly confirmed database."""

import argparse

from app.database.guest_access import configure_guest_access
from app.database.session import get_setup_engine

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-database", required=True)
    args = parser.parse_args()
    engine = get_setup_engine()
    if engine.url.database != args.confirm_database:
        parser.error("Database confirmation does not match configured target")
    configure_guest_access(engine)
    print("Guest TEMP role configured. No personal records modified.")
