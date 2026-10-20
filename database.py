"""Small SQLite/Postgres database layer with a bounded Postgres pool."""

from contextlib import contextmanager
import os
import sqlite3
import threading


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SQLITE_PATH = os.path.join(BASE_DIR, "natal.db")
DATABASE_URL = (
    os.environ.get("DATABASE_URL", "").strip()
    or os.environ.get("POSTGRES_URL", "").strip()
)
USE_POSTGRES = DATABASE_URL.startswith(("postgres://", "postgresql://"))


class PostgresConnection:
    def __init__(self, connection):
        self._connection = connection

    @staticmethod
    def _sql(statement):
        # All SQL in this project uses question-mark placeholders and avoids
        # literal question marks, allowing the same statements on both engines.
        return statement.replace("?", "%s")

    def execute(self, statement, parameters=()):
        return self._connection.execute(self._sql(statement), parameters)

    def executemany(self, statement, parameter_rows):
        cursor = self._connection.cursor()
        cursor.executemany(self._sql(statement), parameter_rows)
        return cursor


_pool = None
_pool_lock = threading.Lock()


def _get_pool():
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                from psycopg.rows import dict_row
                from psycopg_pool import ConnectionPool

                max_size = min(max(int(os.environ.get("DB_POOL_MAX", "3")), 1), 8)
                _pool = ConnectionPool(
                    conninfo=DATABASE_URL,
                    min_size=0,
                    max_size=max_size,
                    timeout=8,
                    max_lifetime=300,
                    max_idle=45,
                    num_workers=1,
                    kwargs={"row_factory": dict_row},
                    open=False,
                )
                _pool.open(wait=False)
    return _pool


@contextmanager
def connect_db():
    if USE_POSTGRES:
        with _get_pool().connection() as connection:
            yield PostgresConnection(connection)
        return
    if os.environ.get("VERCEL"):
        raise RuntimeError("Configure DATABASE_URL para um PostgreSQL persistente no Vercel.")

    connection = sqlite3.connect(SQLITE_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db(seed_defaults=True):
    id_column = "BIGSERIAL PRIMARY KEY" if USE_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"
    email_column = "TEXT NOT NULL UNIQUE" if USE_POSTGRES else "TEXT NOT NULL UNIQUE COLLATE NOCASE"

    with connect_db() as conn:
        if USE_POSTGRES:
            # Serialize first-run seeding if Vercel starts multiple instances together.
            conn.execute("SELECT pg_advisory_xact_lock(?)", (724319501,))
        conn.execute(
            f"""CREATE TABLE IF NOT EXISTS ideas (
                id {id_column},
                sector TEXT,
                idea TEXT,
                status TEXT
            )"""
        )
        conn.execute(
            f"""CREATE TABLE IF NOT EXISTS users (
                id {id_column},
                email {email_column},
                password_hash TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                session_version INTEGER NOT NULL DEFAULT 0,
                created_at BIGINT NOT NULL
            )"""
        )
        activity_id_column = (
            "BIGSERIAL PRIMARY KEY" if USE_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"
        )
        conn.execute(
            f"""CREATE TABLE IF NOT EXISTS idea_activity (
                id {activity_id_column},
                idea_id BIGINT,
                actor_user_id BIGINT,
                actor_email TEXT NOT NULL,
                action TEXT NOT NULL,
                sector TEXT NOT NULL,
                idea TEXT NOT NULL,
                client_ip TEXT,
                from_status TEXT,
                to_status TEXT,
                created_at BIGINT NOT NULL
            )"""
        )
        if USE_POSTGRES:
            conn.execute(
                "ALTER TABLE idea_activity ADD COLUMN IF NOT EXISTS client_ip TEXT"
            )
        else:
            activity_columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(idea_activity)").fetchall()
            }
            if "client_ip" not in activity_columns:
                conn.execute("ALTER TABLE idea_activity ADD COLUMN client_ip TEXT")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_idea_activity_created_at "
            "ON idea_activity (created_at)"
        )
        if USE_POSTGRES:
            conn.execute(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
                "session_version INTEGER NOT NULL DEFAULT 0"
            )
            conn.execute(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
                "role TEXT NOT NULL DEFAULT 'user'"
            )
        else:
            user_columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
            if "session_version" not in user_columns:
                conn.execute(
                    "ALTER TABLE users ADD COLUMN session_version INTEGER NOT NULL DEFAULT 0"
                )
            if "role" not in user_columns:
                conn.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS login_throttles (
                key_hash TEXT PRIMARY KEY,
                attempts INTEGER NOT NULL DEFAULT 0,
                window_started BIGINT NOT NULL,
                blocked_until BIGINT NOT NULL DEFAULT 0
            )"""
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_login_throttles_window "
            "ON login_throttles (window_started)"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ideas_sector ON ideas (sector)")

        idea_count = conn.execute("SELECT COUNT(*) AS count FROM ideas").fetchone()["count"]
        if seed_defaults and idea_count == 0:
            initial_ideas = [
                ("Jardim", "Pisca Pisca", "pendente"),
                ("Jardim", "Boneco de neve", "pendente"),
                ("Hall de Entrada", "Papai Noel Descendo (só perninhas)", "pendente"),
                ("Hall de Entrada", "Refletores vermelho e verde", "pendente"),
                ("Hall do auditorio/Bloco A", "Arvore espiral", "pendente"),
                ("Hall do auditorio/Bloco A", "Enfeite", "pendente"),
                ("Refeitorio", "Geladeira enfeitada", "pendente"),
                ("Refeitorio", "Nuvem de palavras na TV (QR Code e Real Time)", "pendente"),
                ("area jardim", "Fita arvore", "pendente"),
                ("area jardim", "Boneco de neve", "pendente"),
                ("area jardim", "Pisca pisca tipo represa (em fita)", "pendente"),
                ("biblioteca", "+ facilidade de ideias/decorações", "pendente"),
                ("area externa", "Enfeites pinheiro", "pendente"),
                ("porta sala de aula", "Bengalas", "pendente"),
                ("porta sala de aula", "Grilanda/Papai Noel", "pendente"),
            ]
            conn.executemany(
                "INSERT INTO ideas (sector, idea, status) VALUES (?, ?, ?)", initial_ideas
            )
