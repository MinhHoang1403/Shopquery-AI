"""Migrate an explicitly configured restored TEST clone, never the application DB."""

import json

from app.auth.repository import AuthRepository
from app.database.integrity import legacy_fingerprints
from app.database.migrations import migrate_ownership
from app.database.session import get_setup_engine
from app.database.setup import create_schema
from app.database.test_safety import require_test_database


def main() -> None:
    engine = get_setup_engine()
    require_test_database(engine.url.render_as_string(hide_password=False))
    before = legacy_fingerprints(engine)
    create_schema(engine)
    owner = AuthRepository(engine).identity(
        "synthetic-migration-rehearsal", "migration@example.invalid", "Synthetic migration owner"
    )
    migrate_ownership(engine, owner)
    after = legacy_fingerprints(engine)
    if before != after:
        raise RuntimeError("Legacy fingerprints changed during migration")
    migrate_ownership(engine, owner)
    if after != legacy_fingerprints(engine):
        raise RuntimeError("Repeated migration changed legacy data")
    print(
        json.dumps(
            {
                "database": engine.url.database,
                "preserved": before == after,
                "repeat_preserved": True,
                "resources": after,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
