"""Run only after backup restore rehearsal and explicit database approval."""

import argparse
from uuid import UUID

from app.database.migrations import migrate_ownership
from app.database.session import get_setup_engine


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner-user-id", required=True, type=UUID)
    parser.add_argument("--confirm-database", required=True)
    parser.add_argument("--backup-restored", action="store_true", required=True)
    args = parser.parse_args()
    engine = get_setup_engine()
    if args.confirm_database != engine.url.database:
        parser.error("Database confirmation does not match the configured target")
    migrate_ownership(engine, args.owner_user_id)
    print("Ownership migration completed. No seed or embedding was performed.")


if __name__ == "__main__":
    main()
