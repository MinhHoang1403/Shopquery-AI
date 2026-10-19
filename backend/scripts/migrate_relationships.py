"""Install JOIN metadata only after explicit approval and a verified backup restore."""

import argparse
from uuid import UUID

from app.database.join_migration import migrate_relationships
from app.database.session import get_setup_engine


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-database", required=True)
    parser.add_argument("--backup-restored", action="store_true", required=True)
    parser.add_argument("--owner-user-id", type=UUID)
    args = parser.parse_args()
    engine = get_setup_engine()
    if args.confirm_database != engine.url.database:
        parser.error("Database confirmation does not match the configured target")
    migrate_relationships(engine, args.owner_user_id)
    print("JOIN metadata installed. Existing uploads and ownership were not modified.")


if __name__ == "__main__":
    main()
