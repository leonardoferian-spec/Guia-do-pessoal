"""Manage access without placing passwords in command history."""

import getpass
import sys
import time

from werkzeug.security import generate_password_hash

from app import connect_db, init_db


USAGE = """Comandos:
  python manage_users.py list
  python manage_users.py add email@exemplo.com
  python manage_users.py add-admin email@exemplo.com
  python manage_users.py reset-password email@exemplo.com
  python manage_users.py disable email@exemplo.com
  python manage_users.py enable email@exemplo.com"""


def read_new_password():
    password = getpass.getpass("Senha (mínimo 12 caracteres): ")
    confirmation = getpass.getpass("Repita a senha: ")
    if len(password) < 12:
        print("A senha precisa ter pelo menos 12 caracteres.")
        return None
    if password != confirmation:
        print("As senhas não correspondem.")
        return None
    return password


def main():
    if len(sys.argv) not in {2, 3}:
        print(USAGE)
        return 2

    action = sys.argv[1]
    email = sys.argv[2].strip().lower() if len(sys.argv) == 3 else None
    if action not in {"list", "add", "add-admin", "reset-password", "disable", "enable"}:
        print(USAGE)
        return 2
    if (action == "list") != (email is None):
        print(USAGE)
        return 2
    if email is not None and ("@" not in email or email.startswith("@") or email.endswith("@")):
        print("Informe um e-mail válido.")
        return 2

    init_db()

    if action == "list":
        with connect_db() as conn:
            users = conn.execute("SELECT email, is_active, role FROM users ORDER BY email").fetchall()
        if not users:
            print("Nenhuma conta cadastrada.")
        for user in users:
            state = "ativa" if user["is_active"] else "desativada"
            print(f"{user['email']} — {state} — {user['role']}")
        return 0

    if action in {"add", "add-admin"}:
        password = read_new_password()
        if password is None:
            return 2
        with connect_db() as conn:
            existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
            if existing:
                print("Já existe uma conta com esse e-mail.")
                return 1
            conn.execute(
                "INSERT INTO users (email, password_hash, created_at, role) VALUES (?, ?, ?, ?)",
                (email, generate_password_hash(password), int(time.time()),
                 "admin" if action == "add-admin" else "user"),
            )
        print(f"Conta {'administradora' if action == 'add-admin' else 'criada'} para {email}.")
        return 0

    if action == "reset-password":
        password = read_new_password()
        if password is None:
            return 2
        with connect_db() as conn:
            cursor = conn.execute(
                "UPDATE users SET password_hash = ?, session_version = session_version + 1 "
                "WHERE email = ?",
                (generate_password_hash(password), email),
            )
        if not cursor.rowcount:
            print("Não existe conta com esse e-mail.")
            return 1
        print(f"Senha redefinida para {email}.")
        return 0

    active = 0 if action == "disable" else 1
    with connect_db() as conn:
        if active:
            cursor = conn.execute("UPDATE users SET is_active = 1 WHERE email = ?", (email,))
        else:
            cursor = conn.execute(
                "UPDATE users SET is_active = 0, session_version = session_version + 1 "
                "WHERE email = ?",
                (email,),
            )
    if not cursor.rowcount:
        print("Não existe conta com esse e-mail.")
        return 1
    print(f"Conta {email}: {'desativada' if not active else 'ativada'}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
