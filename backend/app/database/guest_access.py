"""Explicit, idempotent permission setup; does not alter personal content."""

from sqlalchemy import Engine, text


def configure_guest_access(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(71948102)"))
        connection.execute(
            text("""
            DO $$ BEGIN
              IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='shopquery_guest') THEN
                CREATE ROLE shopquery_guest NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
                  NOINHERIT NOREPLICATION NOBYPASSRLS;
              END IF;
            END $$;
        """)
        )
        unsafe = connection.scalar(
            text(
                "SELECT rolcanlogin OR rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication "
                "OR rolbypassrls OR EXISTS (SELECT 1 FROM pg_auth_members WHERE member=r.oid) "
                "FROM pg_roles r WHERE rolname='shopquery_guest'"
            )
        )
        if unsafe:
            raise ValueError("Existing guest role has unexpected permissions; refusing setup")
        quote = engine.dialect.identifier_preparer.quote
        connection.execute(
            text(
                f"GRANT CONNECT, TEMPORARY ON DATABASE {quote(engine.url.database)} "
                "TO shopquery_guest"
            )
        )
        connection.execute(text("REVOKE CREATE ON SCHEMA public FROM PUBLIC"))
        connection.execute(text("REVOKE ALL ON SCHEMA public, uploaded_data FROM shopquery_guest"))
        connection.execute(
            text("REVOKE ALL ON ALL TABLES IN SCHEMA public, uploaded_data FROM shopquery_guest")
        )
        if connection.scalar(
            text(
                "SELECT EXISTS (SELECT 1 FROM pg_class c "
                "JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname IN ('public', 'uploaded_data') AND c.relkind IN ('r','p') "
                "AND has_table_privilege('shopquery_guest', c.oid, "
                "'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER'))"
            )
        ):
            raise ValueError("Guest role still has persistent table privileges; refusing setup")
