"""Tiny, safe database upgrade for columns added after a table already existed.

`Base.metadata.create_all()` creates NEW tables, but it never adds new columns to a table
that is already in your database. Feature 6 adds three optional columns to `suppliers`.
This function adds them to an older database (your local inventory.db or the Replit one)
so nobody has to delete their data.

Rules that keep it safe:
  * it only ADDS columns, and only nullable ones (existing rows get NULL);
  * it checks first, so running it on every start-up is harmless;
  * it never drops, renames or changes anything.
"""
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

# table -> [(column name, SQL type)]
ADDED_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "suppliers": [
        ("address", "VARCHAR(255)"),
        ("notes", "VARCHAR(500)"),
        ("updated_at", "DATETIME"),
    ],
}


def upgrade_schema(engine: Engine) -> list[str]:
    """Add any missing columns from ADDED_COLUMNS. Returns what was added, e.g. ['suppliers.address']."""
    inspector = inspect(engine)
    added: list[str] = []
    with engine.begin() as connection:
        for table, columns in ADDED_COLUMNS.items():
            if not inspector.has_table(table):
                continue  # create_all will make it with every column
            existing = {column["name"] for column in inspector.get_columns(table)}
            for name, sql_type in columns:
                if name not in existing:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}"))
                    added.append(f"{table}.{name}")
    return added
