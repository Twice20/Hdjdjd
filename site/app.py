# -*- coding: utf-8 -*-
"""Форум: Flask + SQLite. Вход только через Google. Роли с плашками у ника."""
import os, re, sqlite3, secrets, time, uuid
from functools import wraps
import requests, jinja2
from flask import (Flask, g, request, session, redirect, abort, flash,
                   render_template, send_from_directory, url_for)

E = os.environ.get
BASE_URL = E("BASE_URL", "http://localhost:8080").rstrip("/")
DATA = E("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))
UPLOADS = os.path.join(DATA, "uploads")
os.makedirs(UPLOADS, exist_ok=True)
GID, GSECRET = E("GOOGLE_CLIENT_ID", ""), E("GOOGLE_CLIENT_SECRET", "")
OWNER_EMAIL = E("OWNER_EMAIL", "").strip().lower()
SITE_NAME = E("SITE_NAME", "Forum")

ROLES = {"owner": "OWNER", "admin": "ADMIN", "mod": "MODERATOR", "vip": "VIP", "member": "MEMBER"}
STAFF, ADMINS = {"owner", "admin", "mod"}, {"owner", "admin"}
IMG = {"png": b"\x89PNG", "jpg": b"\xff\xd8\xff", "jpeg": b"\xff\xd8\xff", "gif": b"GIF8", "webp": b"RIFF"}
FILES = {"zip", "rar", "7z", "txt", "pdf"}

app = Flask(__name__)
app.secret_key = E("SECRET_KEY") or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=BASE_URL.startswith("https"),
    MAX_CONTENT_LENGTH=25 * 1024 * 1024, PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 14)
if E("TRUST_PROXY") == "1":
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# ---------- БД ----------
SCHEMA = """
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, gid TEXT UNIQUE, email TEXT, name TEXT, avatar TEXT,
  role TEXT DEFAULT 'member', title TEXT DEFAULT '', banned INTEGER DEFAULT 0, created INTEGER);
CREATE TABLE IF NOT EXISTS cats(id INTEGER PRIMARY KEY, name TEXT, descr TEXT DEFAULT '', staff_only INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS topics(id INTEGER PRIMARY KEY, cat_id INTEGER, user_id INTEGER, title TEXT, created INTEGER, pinned INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS posts(id INTEGER PRIMARY KEY, topic_id INTEGER, user_id INTEGER, body TEXT, created INTEGER);
CREATE TABLE IF NOT EXISTS files(id INTEGER PRIMARY KEY, post_id INTEGER, name TEXT, stored TEXT, is_img INTEGER, size INTEGER);
"""
def db():
    if "db" not in g:
        g.db = sqlite3.connect(os.path.join(DATA, "forum.db")); g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db
@app.teardown_appcontext
def _close(_):
    d = g.pop("db", None)
    if d: d.close()
def q(sql, a=(), one=False):
    cur = db().execute(sql, a); r = cur.fetchall(); db().commit()
    return (r[0] if r else None) if one else r
with app.app_context():
    db().executescript(SCHEMA)
    if not q("SELECT 1 FROM cats LIMIT 1"):
        for n, d, s in (("Announcements", "Новости и правила", 1), ("General", "Общий раздел", 0)):
            q("INSERT INTO cats(name,descr,staff_only) VALUES(?,?,?)", (n, d, s))

# ---------- Безопасность ----------
HITS = {}
def limited(key, n=8, per=60):
    now = time.time(); k = (request.remote_addr, key)
    HITS[k] = [t for t in HITS.get(k, []) if now - t < per]
    if len(HITS[k]) >= n: return True
    HITS[k].append(now); return False
def csrf():
    if "csrf" not in session: session["csrf"] = secrets.token_hex(16)
    return session["csrf"]
@app.before_request
def guard():
    g.user = None
    if "uid" in session:
        g.user = q("SELECT * FROM users WHERE id=?", (session["uid"],), one=True)
        if not g.user or g.user["banned"]: session.clear(); g.user = None
    if request.method == "POST" and not secrets.compare_digest(request.form.get("_csrf", ""), session.get("csrf", "x")):
        abort(400)
@app.after_request
def headers(r):
    r.headers["X-Content-Type-Options"] = "nosniff"
    r.headers["X-Frame-Options"] = "DENY"
    r.headers["Referrer-Policy"] = "same-origin"
    r.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' https: data:; style-src 'self' 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'"
    if BASE_URL.startswith("https"): r.headers["Strict-Transport-Security"] = "max-age=31536000"
    return r
def login_required(f):
    @wraps(f)
    def w(*a, **k):
        if not g.user: return redirect("/login")
        return f(*a, **k)
    return w
def role_required(roles):
    def deco(f):
        @wraps(f)
        @login_required
        def w(*a, **k):
            if g.user["role"] not in roles: abort(403)
            return f(*a, **k)
        return w
    return deco

# ---------- Вход через Google ----------
@app.route("/login")
def login():
    if not GID: return "Google OAuth не настроен (GOOGLE_CLIENT_ID).", 500
    if limited("login", 15): abort(429)
    session["state"] = secrets.token_urlsafe(24)
    p = {"client_id": GID, "redirect_uri": BASE_URL + "/auth/callback", "response_type": "code",
         "scope": "openid email profile", "state": session["state"], "prompt": "select_account"}
    return redirect("https://accounts.google.com/o/oauth2/v2/auth?" + requests.compat.urlencode(p))
@app.route("/auth/callback")
def callback():
    if not session.get("state") or request.args.get("state") != session.get("state") or "code" not in request.args:
        abort(400)
    try:
        t = requests.post("https://oauth2.googleapis.com/token", timeout=10, data={
            "code": request.args["code"], "client_id": GID, "client_secret": GSECRET,
            "redirect_uri": BASE_URL + "/auth/callback", "grant_type": "authorization_code"}).json()
        u = requests.get("https://openidconnect.googleapis.com/v1/userinfo", timeout=10,
                         headers={"Authorization": "Bearer " + t["access_token"]}).json()
        assert u.get("email_verified") and u.get("sub")
    except Exception:
        return "Ошибка входа через Google.", 400
    email = u["email"].lower()
    row = q("SELECT * FROM users WHERE gid=?", (u["sub"],), one=True)
    if not row:
        q("INSERT INTO users(gid,email,name,avatar,role,created) VALUES(?,?,?,?,?,?)",
          (u["sub"], email, (u.get("name") or email.split("@")[0])[:32], u.get("picture", ""),
           "owner" if email == OWNER_EMAIL else "member", int(time.time())))
        row = q("SELECT * FROM users WHERE gid=?", (u["sub"],), one=True)
    elif email == OWNER_EMAIL and row["role"] != "owner":
        q("UPDATE users SET role='owner' WHERE id=?", (row["id"],))
    if row["banned"]: return "Аккаунт заблокирован.", 403
    session.clear(); session["uid"] = row["id"]; session.permanent = True
    return redirect("/")
@app.route("/logout", methods=["POST"])
def logout():
    session.clear(); return redirect("/")

# ---------- Страницы ----------
def can_post(cat): return g.user and (not cat["staff_only"] or g.user["role"] in STAFF)
@app.route("/")
def index():
    cats = q("""SELECT c.*, (SELECT COUNT(*) FROM topics t WHERE t.cat_id=c.id) n FROM cats c ORDER BY c.id""")
    return render_template("index.html", cats=cats)
@app.route("/c/<int:cid>")
def cat(cid):
    c = q("SELECT * FROM cats WHERE id=?", (cid,), one=True) or abort(404)
    ts = q("""SELECT t.*, u.name, u.role, u.title, (SELECT COUNT(*)-1 FROM posts p WHERE p.topic_id=t.id) rep
              FROM topics t JOIN users u ON u.id=t.user_id WHERE cat_id=? ORDER BY pinned DESC, t.id DESC LIMIT 100""", (cid,))
    return render_template("cat.html", c=c, ts=ts, can=can_post(c))
@app.route("/c/<int:cid>/new", methods=["POST"])
@login_required
def new_topic(cid):
    c = q("SELECT * FROM cats WHERE id=?", (cid,), one=True) or abort(404)
    if not can_post(c): abort(403)
    if limited("post", 5): abort(429)
    title, body = request.form.get("title", "").strip()[:120], request.form.get("body", "").strip()[:10000]
    if not title or not body: flash("Заполните заголовок и текст"); return redirect(f"/c/{cid}")
    tid = db().execute("INSERT INTO topics(cat_id,user_id,title,created) VALUES(?,?,?,?)",
                       (cid, g.user["id"], title, int(time.time()))).lastrowid
    db().commit(); add_post(tid, body)
    return redirect(f"/t/{tid}")
def add_post(tid, body):
    pid = db().execute("INSERT INTO posts(topic_id,user_id,body,created) VALUES(?,?,?,?)",
                       (tid, g.user["id"], body, int(time.time()))).lastrowid
    db().commit()
    f = request.files.get("file")
    if f and f.filename:
        ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
        head = f.stream.read(12); f.stream.seek(0)
        if ext in IMG and head.startswith(IMG[ext]): img = 1
        elif ext in FILES: img = 0
        else: flash("Тип файла не разрешён"); return pid
        stored = uuid.uuid4().hex + "." + ext; f.save(os.path.join(UPLOADS, stored))
        q("INSERT INTO files(post_id,name,stored,is_img,size) VALUES(?,?,?,?,?)",
          (pid, re.sub(r"[^\w.\- ]", "_", f.filename)[:80], stored, img, os.path.getsize(os.path.join(UPLOADS, stored))))
    return pid
@app.route("/t/<int:tid>")
def topic(tid):
    t = q("SELECT t.*, c.name cname FROM topics t JOIN cats c ON c.id=t.cat_id WHERE t.id=?", (tid,), one=True) or abort(404)
    ps = q("""SELECT p.*, u.name, u.avatar, u.role, u.title FROM posts p JOIN users u ON u.id=p.user_id
              WHERE topic_id=? ORDER BY p.id LIMIT 300""", (tid,))
    fl = {}
    for f in q("SELECT * FROM files WHERE post_id IN (SELECT id FROM posts WHERE topic_id=?)", (tid,)):
        fl.setdefault(f["post_id"], []).append(f)
    return render_template("topic.html", t=t, ps=ps, fl=fl)
def del_topic(tid):
    for f in q("SELECT stored FROM files WHERE post_id IN (SELECT id FROM posts WHERE topic_id=?)", (tid,)):
        try: os.remove(os.path.join(UPLOADS, f["stored"]))
        except OSError: pass
    q("DELETE FROM files WHERE post_id IN (SELECT id FROM posts WHERE topic_id=?)", (tid,))
    q("DELETE FROM posts WHERE topic_id=?", (tid,)); q("DELETE FROM topics WHERE id=?", (tid,))
@app.route("/t/<int:tid>/reply", methods=["POST"])
@login_required
def reply(tid):
    q("SELECT 1 FROM topics WHERE id=?", (tid,), one=True) or abort(404)
    body = request.form.get("body", "").strip()[:10000]
    if not body: return redirect(f"/t/{tid}")
    if not body.startswith("/") and limited("post", 5): abort(429)
    if body.startswith("/"):                      # команды: /del <id> | /del topic | /pin
        if g.user["role"] not in STAFF: flash("Команды доступны только персоналу"); return redirect(f"/t/{tid}")
        m = re.fullmatch(r"/del\s+(\d+|topic)", body) or re.fullmatch(r"/(pin)", body)
        if not m: flash("Команды: /del <id поста>, /del topic, /pin"); return redirect(f"/t/{tid}")
        if body == "/pin":
            q("UPDATE topics SET pinned=1-pinned WHERE id=?", (tid,)); flash("Закрепление изменено"); return redirect(f"/t/{tid}")
        if m.group(1) == "topic":
            del_topic(tid); flash("Тема удалена"); return redirect("/")
        pid = int(m.group(1)); p = q("SELECT * FROM posts WHERE id=? AND topic_id=?", (pid, tid), one=True)
        if not p: flash("Пост не найден в этой теме"); return redirect(f"/t/{tid}")
        if p["id"] == q("SELECT MIN(id) m FROM posts WHERE topic_id=?", (tid,), one=True)["m"]:
            del_topic(tid); flash("Тема удалена"); return redirect("/")
        q("DELETE FROM files WHERE post_id=?", (pid,)); q("DELETE FROM posts WHERE id=?", (pid,))
        flash(f"Пост #{pid} удалён"); return redirect(f"/t/{tid}")
    add_post(tid, body); return redirect(f"/t/{tid}#end")

# Файлы и превью — только для вошедших
def get_file(fid): return q("SELECT * FROM files WHERE id=?", (fid,), one=True) or abort(404)
@app.route("/file/<int:fid>")
@login_required
def download(fid):
    f = get_file(fid)
    return send_from_directory(UPLOADS, f["stored"], as_attachment=True, download_name=f["name"])
@app.route("/preview/<int:fid>")
@login_required
def preview(fid):
    f = get_file(fid)
    if not f["is_img"]: abort(404)
    return send_from_directory(UPLOADS, f["stored"], as_attachment=False)

# ---------- Админка ----------
@app.route("/admin")
@role_required(ADMINS)
def admin():
    return render_template("admin.html", users=q("SELECT * FROM users ORDER BY id"),
                           cats=q("SELECT * FROM cats ORDER BY id"), n=len(q("SELECT id FROM topics")))
@app.route("/admin/user", methods=["POST"])
@role_required(ADMINS)
def admin_user():
    u = q("SELECT * FROM users WHERE id=?", (request.form.get("id", 0),), one=True) or abort(404)
    role = request.form.get("role", u["role"])
    if role not in ROLES or u["role"] == "owner" and g.user["role"] != "owner": abort(403)
    if role in ADMINS and g.user["role"] != "owner": abort(403)      # админов назначает только owner
    if u["role"] in ADMINS and g.user["role"] != "owner": abort(403)
    if u["id"] == g.user["id"]: flash("Себя менять нельзя"); return redirect("/admin")
    q("UPDATE users SET role=?, title=?, banned=? WHERE id=?",
      (role, request.form.get("title", "")[:24], 1 if request.form.get("banned") else 0, u["id"]))
    flash("Сохранено"); return redirect("/admin")
@app.route("/admin/cat", methods=["POST"])
@role_required(ADMINS)
def admin_cat():
    n = request.form.get("name", "").strip()[:60]
    if n: q("INSERT INTO cats(name,descr,staff_only) VALUES(?,?,?)", (n, request.form.get("descr", "")[:200], 1 if request.form.get("staff_only") else 0))
    return redirect("/admin")
@app.route("/admin/cat/<int:cid>/delete", methods=["POST"])
@role_required(ADMINS)
def admin_cat_del(cid):
    for t in q("SELECT id FROM topics WHERE cat_id=?", (cid,)): del_topic(t["id"])
    q("DELETE FROM cats WHERE id=?", (cid,)); return redirect("/admin")

from templates import TEMPLATES
app.jinja_loader = jinja2.DictLoader(TEMPLATES)
app.jinja_env.globals.update(csrf=csrf, ROLES=ROLES, SITE_NAME=SITE_NAME, STAFF=STAFF,
                             user=lambda: g.user)
app.jinja_env.filters["dt"] = lambda t: time.strftime("%d.%m.%Y %H:%M", time.gmtime(t))

if __name__ == "__main__":
    from waitress import serve
    serve(app, host="0.0.0.0", port=int(E("PORT", "8080")), max_request_body_size=26 * 1024 * 1024)
