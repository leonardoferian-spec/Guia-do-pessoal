import hashlib
import hmac
import ipaddress
import os
import secrets
import threading
import time
from datetime import timedelta

from flask import Flask, abort, flash, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SECRET_FILE = os.path.join(BASE_DIR, ".app_secret_key")
ENV_FILE = os.path.join(BASE_DIR, ".env")


def load_local_env():
    if not os.path.isfile(ENV_FILE):
        return
    with open(ENV_FILE, "r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            name, value = name.strip(), value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            if name and name not in os.environ:
                os.environ[name] = value


load_local_env()

from database import connect_db, init_db


def load_secret_key():
    key = os.environ.get("APP_SECRET_KEY")
    if key:
        return key
    if os.environ.get("VERCEL"):
        raise RuntimeError("Configure APP_SECRET_KEY nas variáveis de ambiente do Vercel.")
    try:
        with open(SECRET_FILE, "x", encoding="utf-8") as secret_file:
            key = secrets.token_urlsafe(48)
            secret_file.write(key)
            return key
    except FileExistsError:
        with open(SECRET_FILE, "r", encoding="utf-8") as secret_file:
            return secret_file.read().strip()


app = Flask(__name__, static_folder=os.path.join(BASE_DIR, "public"), static_url_path="")
app.config.update(
    SECRET_KEY=load_secret_key(),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=(
        os.environ.get("VERCEL") == "1"
        or os.environ.get("COOKIE_SECURE", "0").lower() in {"1", "true", "yes"}
    ),
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    MAX_CONTENT_LENGTH=64 * 1024,
    MAX_FORM_MEMORY_SIZE=16 * 1024,
)

_db_initialized = False
_db_initialization_lock = threading.Lock()


@app.before_request
def ensure_database_ready():
    global _db_initialized
    if _db_initialized:
        return None
    with _db_initialization_lock:
        if not _db_initialized:
            init_db()
            _db_initialized = True
    return None


def csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


app.jinja_env.globals["csrf_token"] = csrf_token


@app.before_request
def authenticate_and_check_csrf():
    endpoint = request.endpoint
    if endpoint in {"static", "login", "credits"}:
        pass
    elif session.get("user_id"):
        with connect_db() as conn:
            g.user = conn.execute(
                "SELECT id, email, role, session_version FROM users WHERE id = ? AND is_active = 1",
                (session["user_id"],),
            ).fetchone()
        if g.user and session.get("user_version") != g.user["session_version"]:
            g.user = None
        if g.user is None:
            session.clear()
            if endpoint != "login":
                if request.path.startswith("/api/"):
                    return jsonify({"error": "Autenticação necessária."}), 401
                return redirect(url_for("login"))
    else:
        if endpoint != "login":
            if request.path.startswith("/api/"):
                return jsonify({"error": "Autenticação necessária."}), 401
            return redirect(url_for("login"))

    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        expected = session.get("csrf_token", "")
        supplied = request.form.get("csrf_token") or request.headers.get("X-CSRFToken", "")
        if not expected or not hmac.compare_digest(expected, supplied):
            abort(400, description="Token de segurança inválido. Atualize a página e tente novamente.")


@app.after_request
def add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), geolocation=(), microphone=()")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; base-uri 'self'; object-src 'none'; "
        "frame-ancestors 'none'; form-action 'self'; script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data:",
    )
    response.headers.setdefault("Cache-Control", "no-store")
    if os.environ.get("VERCEL") == "1":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


def login_throttle_key(email):
    if os.environ.get("VERCEL") == "1":
        client_ip = request.headers.get("x-forwarded-for", "").strip()
    else:
        client_ip = request.remote_addr or ""
    material = f"{email}\0{client_ip or 'unknown'}".encode("utf-8")
    return hmac.new(app.secret_key.encode(), material, hashlib.sha256).hexdigest()


def is_login_throttled(key, now):
    with connect_db() as conn:
        row = conn.execute(
            "SELECT attempts, window_started, blocked_until FROM login_throttles WHERE key_hash = ?",
            (key,),
        ).fetchone()
    return bool(row and row["window_started"] > now - 900 and row["blocked_until"] > now)


def record_failed_login(key, now):
    cutoff = now - 900
    with connect_db() as conn:
        conn.execute("DELETE FROM login_throttles WHERE window_started < ?", (now - 86400,))
        conn.execute(
            "INSERT INTO login_throttles (key_hash, attempts, window_started, blocked_until) "
            "VALUES (?, 1, ?, 0) ON CONFLICT (key_hash) DO UPDATE SET "
            "attempts = CASE WHEN login_throttles.window_started <= ? THEN 1 "
            "ELSE login_throttles.attempts + 1 END, "
            "window_started = CASE WHEN login_throttles.window_started <= ? THEN excluded.window_started "
            "ELSE login_throttles.window_started END, "
            "blocked_until = CASE WHEN login_throttles.window_started > ? "
            "AND login_throttles.attempts >= 9 THEN excluded.window_started + 300 "
            "ELSE login_throttles.blocked_until END",
            (key, now, cutoff, cutoff, cutoff),
        )


def get_client_ip():
    # Vercel replaces X-Forwarded-For with the public client IP at its edge.
    candidate = (
        request.headers.get("x-forwarded-for", "")
        if os.environ.get("VERCEL") == "1"
        else request.remote_addr or ""
    ).strip().split(",", 1)[0].strip()
    try:
        return str(ipaddress.ip_address(candidate)) if candidate else None
    except ValueError:
        return None


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("index"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()[:254]
        password = request.form.get("password", "")
        throttle_key = login_throttle_key(email)
        now = int(time.time())
        if is_login_throttled(throttle_key, now):
            flash("Muitas tentativas. Aguarde alguns minutos e tente novamente.", "error")
            return render_template("login.html"), 429
        with connect_db() as conn:
            user = conn.execute(
                "SELECT id, email, password_hash, session_version "
                "FROM users WHERE email = ? AND is_active = 1",
                (email,),
            ).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            with connect_db() as conn:
                conn.execute("DELETE FROM login_throttles WHERE key_hash = ?", (throttle_key,))
            session.clear()
            session["user_id"] = user["id"]
            session["user_version"] = user["session_version"]
            session["csrf_token"] = secrets.token_urlsafe(32)
            session.permanent = True
            return redirect(url_for("index"))
        else:
            record_failed_login(throttle_key, now)
            flash("E-mail ou senha inválidos.", "error")
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
def index():
    return render_template(
        "index.html", user_email=g.user["email"], is_admin=g.user["role"] == "admin"
    )


@app.route("/credits")
def credits():
    back_url = url_for("index") if session.get("user_id") else url_for("login")
    return render_template("credits.html", back_url=back_url)


@app.route("/account/password", methods=["GET", "POST"])
def change_password():
    error = None
    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirmation = request.form.get("confirm_password", "")
        with connect_db() as conn:
            user = conn.execute(
                "SELECT password_hash, session_version FROM users WHERE id = ? AND is_active = 1",
                (g.user["id"],),
            ).fetchone()
        if not user or not check_password_hash(user["password_hash"], current_password):
            error = "A senha atual está incorreta."
        elif len(new_password) < 12:
            error = "A nova senha precisa ter pelo menos 12 caracteres."
        elif new_password != confirmation:
            error = "A confirmação não corresponde à nova senha."
        else:
            new_hash = generate_password_hash(new_password)
            with connect_db() as conn:
                cursor = conn.execute(
                    "UPDATE users SET password_hash = ?, session_version = session_version + 1 "
                    "WHERE id = ? AND password_hash = ? AND is_active = 1",
                    (new_hash, g.user["id"], user["password_hash"]),
                )
                if cursor.rowcount:
                    updated = conn.execute(
                        "SELECT session_version FROM users WHERE id = ?", (g.user["id"],)
                    ).fetchone()
                else:
                    updated = None
            if updated:
                session["user_version"] = updated["session_version"]
                session["csrf_token"] = secrets.token_urlsafe(32)
                flash("Sua senha foi alterada. As outras sessões foram encerradas.", "success")
                return redirect(url_for("change_password"))
            error = "A conta mudou durante a operação. Entre novamente e tente de novo."
    return render_template("change_password.html", error=error)


@app.route("/admin/users", methods=["GET", "POST"])
def admin_users():
    if g.user["role"] != "admin":
        abort(403)
    error = None
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirmation = request.form.get("confirm_password", "")
        admin_password = request.form.get("admin_password", "")
        role = request.form.get("role", "user")
        if len(email) > 254 or email.count("@") != 1 or any(char.isspace() for char in email):
            error = "Informe um endereço de e-mail válido."
        elif role not in {"user", "admin"}:
            error = "Perfil inválido."
        elif len(password) < 12:
            error = "A senha inicial precisa ter pelo menos 12 caracteres."
        elif password != confirmation:
            error = "As senhas não correspondem."
        else:
            with connect_db() as conn:
                admin = conn.execute(
                    "SELECT password_hash FROM users WHERE id = ? AND is_active = 1 AND role = 'admin'",
                    (g.user["id"],),
                ).fetchone()
            if not admin or not check_password_hash(admin["password_hash"], admin_password):
                error = "Confirme sua senha de administrador para criar a conta."
        if not error:
            try:
                with connect_db() as conn:
                    conn.execute(
                        "INSERT INTO users (email, password_hash, created_at, role) "
                        "VALUES (?, ?, ?, ?)",
                        (email, generate_password_hash(password), int(time.time()), role),
                    )
                flash(f"Conta {email} criada com perfil {role}.", "success")
                return redirect(url_for("admin_users"))
            except Exception as db_error:
                # Do not return database diagnostics or submitted credentials to the browser.
                app.logger.warning("Could not create a user account (%s).", type(db_error).__name__)
                error = "Não foi possível criar a conta. Confira se esse e-mail já está cadastrado."
    with connect_db() as conn:
        users = conn.execute(
            "SELECT email, role, is_active, created_at FROM users ORDER BY email"
        ).fetchall()
    return render_template("admin_users.html", users=users, error=error)


@app.route("/api/ideas", methods=["GET"])
def get_ideas():
    with connect_db() as conn:
        ideas = [dict(row) for row in conn.execute("SELECT * FROM ideas").fetchall()]
    return jsonify(ideas)


@app.route("/api/ideas", methods=["POST"])
def add_idea():
    data = request.get_json(silent=True) or {}
    sector, idea = str(data.get("sector", "")).strip(), str(data.get("idea", "")).strip()
    if not sector or not idea:
        return jsonify({"error": "Setor e ideia são obrigatórios."}), 400
    if len(sector) > 80 or len(idea) > 180:
        return jsonify({"error": "O setor deve ter até 80 caracteres e a ideia até 180."}), 400
    with connect_db() as conn:
        cursor = conn.execute(
            "INSERT INTO ideas (sector, idea, status) VALUES (?, ?, ?) RETURNING id",
            (sector, idea, "pendente"),
        )
        idea_id = cursor.fetchone()["id"]
        conn.execute(
            "INSERT INTO idea_activity "
            "(idea_id, actor_user_id, actor_email, action, sector, idea, client_ip, from_status, to_status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                idea_id,
                g.user["id"],
                g.user["email"],
                "created",
                sector,
                idea,
                get_client_ip(),
                None,
                "pendente",
                int(time.time()),
            ),
        )
    return jsonify({"id": idea_id}), 201


@app.route("/api/ideas/<int:idea_id>", methods=["PUT"])
def update_idea(idea_id):
    data = request.get_json(silent=True) or {}
    status = data.get("status")
    if status not in {"pendente", "andamento", "concluida"}:
        return jsonify({"error": "Status inválido."}), 400
    with connect_db() as conn:
        idea = conn.execute(
            "SELECT sector, idea, status FROM ideas WHERE id = ?", (idea_id,)
        ).fetchone()
        if not idea:
            return jsonify({"success": False}), 404
        previous_status = idea["status"]
        if previous_status != status:
            conn.execute("UPDATE ideas SET status = ? WHERE id = ?", (status, idea_id))
            conn.execute(
                "INSERT INTO idea_activity "
                "(idea_id, actor_user_id, actor_email, action, sector, idea, client_ip, from_status, to_status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    idea_id,
                    g.user["id"],
                    g.user["email"],
                    "status_changed",
                    idea["sector"] or "Outros",
                    idea["idea"],
                    get_client_ip(),
                    previous_status,
                    status,
                    int(time.time()),
                ),
            )
    return jsonify({"success": True})


@app.route("/api/ideas/<int:idea_id>", methods=["DELETE"])
def delete_idea(idea_id):
    with connect_db() as conn:
        idea = conn.execute(
            "SELECT sector, idea, status FROM ideas WHERE id = ?", (idea_id,)
        ).fetchone()
        if not idea:
            return jsonify({"success": False}), 404
        conn.execute(
            "INSERT INTO idea_activity "
            "(idea_id, actor_user_id, actor_email, action, sector, idea, client_ip, from_status, to_status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                idea_id,
                g.user["id"],
                g.user["email"],
                "deleted",
                idea["sector"] or "Outros",
                idea["idea"],
                get_client_ip(),
                idea["status"],
                None,
                int(time.time()),
            ),
        )
        conn.execute("DELETE FROM ideas WHERE id = ?", (idea_id,))
    return jsonify({"success": True})


@app.route("/api/activity", methods=["GET"])
def get_activity():
    if g.user["role"] != "admin":
        abort(403)
    with connect_db() as conn:
        entries = [
            dict(row)
            for row in conn.execute(
                "SELECT actor_email, action, sector, idea, client_ip, from_status, to_status, created_at "
                "FROM idea_activity ORDER BY id DESC LIMIT 200"
            ).fetchall()
        ]
    return jsonify(entries)


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    host = os.environ.get("HOST", "127.0.0.1")
    debug = os.environ.get("FLASK_DEBUG", "0").lower() in {"1", "true", "yes"}
    app.run(debug=debug, host=host, port=port)
