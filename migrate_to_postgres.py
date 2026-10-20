"""Copy the local SQLite board and existing user accounts into PostgreSQL."""

import sqlite3

from app import init_db
from database import SQLITE_PATH, USE_POSTGRES, connect_db


def main():
    if not USE_POSTGRES:
        raise SystemExit("Configure DATABASE_URL com a conexão PostgreSQL de destino no .env.")

    source = sqlite3.connect(SQLITE_PATH)
    source.row_factory = sqlite3.Row
    init_db(seed_defaults=False)

    with source, connect_db() as target:
        for table, columns in (
            ("ideas", ("id", "sector", "idea", "status")),
            ("users", ("id", "email", "password_hash", "is_active", "session_version", "created_at", "role")),
        ):
            try:
                if table == "users":
                    source_columns = {row["name"] for row in source.execute("PRAGMA table_info(users)")}
                    selected_columns = tuple(column for column in columns if column in source_columns)
                else:
                    selected_columns = columns
                if not selected_columns:
                    continue
                rows = source.execute(f"SELECT {', '.join(selected_columns)} FROM {table}").fetchall()
            except sqlite3.OperationalError:
                if table == "users":
                    continue
                raise
            column_sql = ", ".join(selected_columns)
            placeholders = ", ".join("?" for _ in selected_columns)
            update_sql = ", ".join(f"{column} = EXCLUDED.{column}" for column in selected_columns[1:])
            sql = (
                f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders}) "
                f"ON CONFLICT (id) DO UPDATE SET {update_sql}"
            )
            target.executemany(sql, [tuple(row[column] for column in selected_columns) for row in rows])

        for table in ("ideas", "users"):
            target.execute(
                "SELECT setval(pg_get_serial_sequence(?, 'id'), "
                f"GREATEST(COALESCE((SELECT MAX(id) FROM {table}), 1), 1), "
                f"EXISTS (SELECT 1 FROM {table}))",
                (table,),
            )

    source.close()
    print("Ideias e contas locais foram copiadas para PostgreSQL.")


if __name__ == "__main__":
    main()
