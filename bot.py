# -*- coding: utf-8 -*-
"""Telegram-бот: принимает zip-архив сайта, разворачивает, перезапускает. Доступ — только владельцу."""
import os, sys, json, shutil, secrets, subprocess, zipfile, time, io, logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

OWNER_ID = int(os.environ.get("OWNER_ID", "8171375787"))
TOKEN = os.environ["BOT_TOKEN"]
ROOT = os.path.dirname(os.path.abspath(__file__))
DATA, SITE = os.path.join(ROOT, "data"), os.path.join(ROOT, "site")
CFG_FILE, LOG = os.path.join(DATA, "config.json"), os.path.join(DATA, "forum.log")
os.makedirs(DATA, exist_ok=True)
KEYS = {"GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "OWNER_EMAIL", "SITE_NAME", "PORT", "TRUST_PROXY"}
SECRET = {"GOOGLE_CLIENT_SECRET"}
MAX_UNPACKED = 200 * 1024 * 1024
proc = None
logging.basicConfig(level=logging.INFO)

def cfg():
    c = json.load(open(CFG_FILE)) if os.path.exists(CFG_FILE) else {}
    if "SECRET_KEY" not in c: c["SECRET_KEY"] = secrets.token_hex(32); save(c)
    c.setdefault("BASE_URL", os.environ.get("BASE_URL", "http://localhost:8080")); c.setdefault("PORT", os.environ.get("PORT", "8080"))
    return c
def save(c): json.dump(c, open(CFG_FILE, "w"), indent=1)

def running(): return proc is not None and proc.poll() is None
def stop():
    global proc
    if running():
        proc.terminate()
        try: proc.wait(10)
        except subprocess.TimeoutExpired: proc.kill()
    proc = None
def start():
    global proc
    stop()
    if not os.path.exists(os.path.join(SITE, "app.py")): return "В site/ нет app.py — пришлите архив."
    env = dict(os.environ, **cfg(), DATA_DIR=DATA)
    env.pop("BOT_TOKEN", None)                       # сайту токен бота не нужен
    proc = subprocess.Popen([sys.executable, "app.py"], cwd=SITE, env=env,
                            stdout=open(LOG, "ab"), stderr=subprocess.STDOUT)
    return "Сайт запущен"

def owner_only(fn):
    async def w(u: Update, c: ContextTypes.DEFAULT_TYPE):
        if not u.effective_user or u.effective_user.id != OWNER_ID or u.effective_chat.type != "private":
            return                                    # чужим не отвечаем вообще
        return await fn(u, c)
    return w

HELP = """Команды:
/status — состояние и настройки
/domain example.com — сменить домен (http:// или https:// можно указать)
/set КЛЮЧ значение — GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, OWNER_EMAIL, SITE_NAME, PORT, TRUST_PROXY
/restart, /stop, /logs
/backup — прислать копию базы и загрузок
/rollback — вернуть предыдущую версию сайта
Пришлите .zip с сайтом (в корне архива должен быть app.py) — он развернётся автоматически."""

@owner_only
async def h_start(u, c): await u.message.reply_text(HELP)
@owner_only
async def h_status(u, c):
    k = cfg(); m = lambda v: "…" + v[-4:] if v else "—"
    await u.message.reply_text(f"Сайт: {'работает' if running() else 'остановлен'}\nURL: {k['BASE_URL']}\nPORT: {k['PORT']}\n"
        f"GOOGLE_CLIENT_ID: {m(k.get('GOOGLE_CLIENT_ID',''))}\nGOOGLE_CLIENT_SECRET: {'задан' if k.get('GOOGLE_CLIENT_SECRET') else '—'}\n"
        f"OWNER_EMAIL: {k.get('OWNER_EMAIL','—')}\nRedirect URI для Google: {k['BASE_URL']}/auth/callback")
@owner_only
async def h_domain(u, c):
    if not c.args: return await u.message.reply_text("Пример: /domain forum.example.com")
    d = c.args[0].strip().rstrip("/")
    if not d.startswith("http"): d = "https://" + d
    if not all(ch.isalnum() or ch in ":/.-_" for ch in d): return await u.message.reply_text("Некорректный домен")
    k = cfg(); k["BASE_URL"] = d; save(k)
    await u.message.reply_text(f"Домен: {d}\n{start()}\nДобавьте в Google Cloud → Redirect URI: {d}/auth/callback")
@owner_only
async def h_set(u, c):
    if len(c.args) < 2 or c.args[0].upper() not in KEYS:
        return await u.message.reply_text("Формат: /set КЛЮЧ значение\nКлючи: " + ", ".join(sorted(KEYS)))
    k = cfg(); key = c.args[0].upper(); k[key] = " ".join(c.args[1:]); save(k)
    if key in SECRET:
        try: await u.message.delete()                  # убираем секрет из чата
        except Exception: pass
    await c.bot.send_message(u.effective_chat.id, f"{key} сохранён. {start()}")
@owner_only
async def h_restart(u, c): await u.message.reply_text(start())
@owner_only
async def h_stop(u, c): stop(); await u.message.reply_text("Сайт остановлен")
@owner_only
async def h_logs(u, c):
    t = open(LOG, "rb").read()[-3500:].decode("utf8", "replace") if os.path.exists(LOG) else "лога нет"
    await u.message.reply_text(t or "пусто")
@owner_only
async def h_backup(u, c):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for base, _, files in os.walk(DATA):
            for f in files:
                p = os.path.join(base, f)
                if f not in ("forum.log", "config.json") and "backups" not in p: z.write(p, os.path.relpath(p, DATA))
    buf.seek(0); buf.name = time.strftime("backup_%Y%m%d_%H%M.zip")
    await u.message.reply_document(buf)

def unpack(path):
    with zipfile.ZipFile(path) as z:
        if sum(i.file_size for i in z.infolist()) > MAX_UNPACKED: raise ValueError("архив слишком большой")
        tmp = os.path.join(DATA, "_new"); shutil.rmtree(tmp, ignore_errors=True); os.makedirs(tmp)
        for i in z.infolist():                         # защита от zip-slip
            t = os.path.realpath(os.path.join(tmp, i.filename))
            if not t.startswith(os.path.realpath(tmp) + os.sep) and t != os.path.realpath(tmp): raise ValueError("опасный путь в архиве")
        z.extractall(tmp)
    top = os.listdir(tmp)
    if len(top) == 1 and os.path.isdir(os.path.join(tmp, top[0])): tmp = os.path.join(tmp, top[0])
    if not os.path.exists(os.path.join(tmp, "app.py")): raise ValueError("в корне архива нет app.py")
    return tmp
@owner_only
async def h_doc(u, c):
    d = u.message.document
    if not d.file_name.lower().endswith(".zip"): return await u.message.reply_text("Нужен .zip")
    if d.file_size > 20 * 1024 * 1024: return await u.message.reply_text("Telegram отдаёт боту файлы до 20 МБ")
    zp = os.path.join(DATA, "_upload.zip"); await (await d.get_file()).download_to_drive(zp)
    try: new = unpack(zp)
    except Exception as e: return await u.message.reply_text(f"Отклонено: {e}")
    stop(); prev = os.path.join(ROOT, "site_prev"); shutil.rmtree(prev, ignore_errors=True)
    if os.path.exists(SITE): shutil.move(SITE, prev)
    shutil.move(new, SITE); shutil.rmtree(os.path.join(DATA, "_new"), ignore_errors=True); os.remove(zp)
    req = os.path.join(SITE, "requirements.txt")
    if os.path.exists(req):
        r = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", req], capture_output=True, text=True)
        if r.returncode: await u.message.reply_text("pip: " + r.stderr[-600:])
    await u.message.reply_text("Архив развёрнут. " + start() + "\nБаза и загрузки (data/) не тронуты.")
@owner_only
async def h_rollback(u, c):
    prev = os.path.join(ROOT, "site_prev")
    if not os.path.exists(prev): return await u.message.reply_text("Предыдущей версии нет")
    stop(); shutil.rmtree(SITE, ignore_errors=True); shutil.move(prev, SITE)
    await u.message.reply_text("Откат выполнен. " + start())

def main():
    app = Application.builder().token(TOKEN).build()
    for n, f in (("start", h_start), ("help", h_start), ("status", h_status), ("domain", h_domain), ("set", h_set),
                 ("restart", h_restart), ("stop", h_stop), ("logs", h_logs), ("backup", h_backup), ("rollback", h_rollback)):
        app.add_handler(CommandHandler(n, f))
    app.add_handler(MessageHandler(filters.Document.ALL, h_doc))
    start()
    app.run_polling(drop_pending_updates=True)
if __name__ == "__main__": main()
