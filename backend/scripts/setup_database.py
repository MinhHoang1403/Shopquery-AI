"""Create the database schema and reader grants."""

from app.database.session import get_setup_engine
from app.database.setup import create_schema

if __name__ == "__main__":
    create_schema(get_setup_engine())
    print("Database schema is ready.")
