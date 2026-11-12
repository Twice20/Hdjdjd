# -*- coding: utf-8 -*-
CSS = """
:root{--bg:#0d0e10;--card:#15171a;--line:#24272c;--tx:#d7dadf;--mut:#7d838c;--ac:#a6d82b}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font:15px/1.55 "Segoe UI",system-ui,sans-serif}
a{color:var(--ac);text-decoration:none}a:hover{text-decoration:underline}
.w{max-width:960px;margin:0 auto;padding:0 14px}
header{border-bottom:1px solid var(--line);background:#101215}
header .w{display:flex;align-items:center;gap:16px;height:54px}
.logo{font-weight:700;font-size:18px;color:#fff;letter-spacing:.5px}.sp{flex:1}
.card{background:var(--card);border:1px solid var(--line);border-radius:6px;margin:14px 0}
.row{display:flex;gap:12px;align-items:center;padding:12px 14px;border-top:1px solid var(--line)}
.row:first-child{border-top:0}.row .m{flex:1;min-width:0}.mut{color:var(--mut);font-size:13px}
h1{font-size:20px;margin:22px 0 4px}
input,textarea,select,button{font:inherit;color:var(--tx);background:#0b0c0e;border:1px solid var(--line);border-radius:5px;padding:8px 10px}
textarea{width:100%;min-height:110px}input[type=text]{width:100%}
button,.btn{background:var(--ac);color:#10130a;border:0;font-weight:600;cursor:pointer;padding:8px 16px;border-radius:5px;display:inline-block}
.btn:hover{text-decoration:none;opacity:.9}button.ghost{background:none;color:var(--mut);border:1px solid var(--line)}
.post{display:flex}.side{width:150px;padding:14px;border-right:1px solid var(--line);text-align:center;flex:none}
.side img,.av{width:64px;height:64px;border-radius:50%;background:#222;object-fit:cover}
.body{flex:1;padding:14px;min-width:0}.txt{white-space:pre-wrap;word-wrap:break-word}
.b{display:inline-block;font-size:11px;font-weight:700;padding:1px 7px;border-radius:3px;margin-top:4px;letter-spacing:.4px}
.b.owner{background:#3a1216;color:#ff5b64;border:1px solid #6b1d24}.b.admin{background:#3a1216;color:#ff7a5b;border:1px solid #6b2a1d}
.b.mod{background:#12302a;color:#4fe0b0;border:1px solid #1d5f4e}.b.vip{background:#2b1a3d;color:#c58bff;border:1px solid #4d2f73}
.b.member{background:#1b1e22;color:var(--mut);border:1px solid var(--line)}
.n.owner,.n.admin{color:#ff6b5e}.n.mod{color:#4fe0b0}.n.vip{color:#c58bff}.n{font-weight:600}
.flash{background:#22260f;border:1px solid #4a5a14;padding:8px 14px;border-radius:5px;margin-top:14px}
.gate{border:1px dashed var(--line);padding:18px;text-align:center;color:var(--mut);border-radius:5px;margin-top:10px}
.pre{max-width:320px;max-height:240px;border-radius:5px;border:1px solid var(--line);display:block;margin-top:8px}
table{width:100%;border-collapse:collapse}td,th{padding:8px 10px;border-top:1px solid var(--line);text-align:left;font-size:14px}
@media(max-width:600px){.post{display:block}.side{width:auto;border:0;border-bottom:1px solid var(--line)}}
"""
BASE = """<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{% block title %}{{ SITE_NAME }}{% endblock %}</title><style>""" + CSS + """</style></head><body>
{% macro badge(role,title) %}<span class="b {{role}}">{{ title or ROLES[role] }}</span>{% endmacro %}
<header><div class="w"><a class="logo" href="/">{{ SITE_NAME }}</a><span class="sp"></span>
{% if user() %}<span class="n {{user().role}}">{{ user().name }}</span>{{ badge(user().role,user().title) }}
{% if user().role in ['owner','admin'] %}<a href="/admin">Админка</a>{% endif %}
<form method="post" action="/logout"><input type="hidden" name="_csrf" value="{{csrf()}}"><button class="ghost">Выйти</button></form>
{% else %}<a class="btn" href="/login">Войти через Google</a>{% endif %}</div></header>
<div class="w">{% for m in get_flashed_messages() %}<div class="flash">{{ m }}</div>{% endfor %}{% block c %}{% endblock %}</div></body></html>"""

INDEX = """{% extends "base.html" %}{% block c %}<h1>Разделы</h1><div class="card">
{% for c in cats %}<div class="row"><div class="m"><a href="/c/{{c.id}}"><b>{{c.name}}</b></a><div class="mut">{{c.descr}}</div></div>
<div class="mut">{{c.n}} тем</div></div>{% endfor %}</div>{% endblock %}"""

CAT = """{% extends "base.html" %}{% block c %}<h1>{{c.name}}</h1><div class="mut">{{c.descr}}</div><div class="card">
{% for t in ts %}<div class="row"><div class="m"><a href="/t/{{t.id}}">{% if t.pinned %}📌 {% endif %}{{t.title}}</a>
<div class="mut"><span class="n {{t.role}}">{{t.name}}</span> · {{t.created|dt}}</div></div><div class="mut">{{t.rep}} отв.</div></div>
{% else %}<div class="row mut">Пока пусто</div>{% endfor %}</div>
{% if can %}<form method="post" action="/c/{{c.id}}/new" enctype="multipart/form-data" class="card" style="padding:14px">
<input type="hidden" name="_csrf" value="{{csrf()}}"><input type="text" name="title" placeholder="Заголовок" maxlength="120" required>
<textarea name="body" placeholder="Текст" required style="margin-top:8px"></textarea>
<p><input type="file" name="file"> <button>Создать тему</button></p></form>
{% elif not user() %}<div class="gate">Чтобы создавать темы, <a href="/login">войдите через Google</a></div>{% endif %}{% endblock %}"""

TOPIC = """{% extends "base.html" %}{% block title %}{{t.title}}{% endblock %}{% block c %}
<h1>{{t.title}}</h1><div class="mut"><a href="/c/{{t.cat_id}}">{{t.cname}}</a></div>
{% for p in ps %}<div class="card post" id="p{{p.id}}"><div class="side">
{% if p.avatar %}<img src="{{p.avatar}}" referrerpolicy="no-referrer" alt="">{% else %}<div class="av" style="margin:auto"></div>{% endif %}
<div class="n {{p.role}}">{{p.name}}</div>{{ badge(p.role,p.title) }}</div>
<div class="body"><div class="mut">#{{p.id}} · {{p.created|dt}}</div><div class="txt">{{p.body}}</div>
{% for f in fl.get(p.id,[]) %}{% if user() %}
{% if f.is_img %}<a href="/preview/{{f.id}}"><img class="pre" src="/preview/{{f.id}}" alt=""></a>{% endif %}
<p><a href="/file/{{f.id}}">⬇ {{f.name}}</a> <span class="mut">({{(f.size/1024)|round|int}} КБ)</span></p>
{% else %}<div class="gate">🔒 Вложение «{{f.name}}» — <a href="/login">войдите</a>, чтобы скачать и посмотреть</div>{% endif %}{% endfor %}
</div></div>{% endfor %}<a id="end"></a>
{% if user() %}<form method="post" action="/t/{{t.id}}/reply" enctype="multipart/form-data" class="card" style="padding:14px">
<input type="hidden" name="_csrf" value="{{csrf()}}"><textarea name="body" required placeholder="Ваш ответ{% if user().role in STAFF %} (команды: /del &lt;id&gt;, /del topic, /pin){% endif %}"></textarea>
<p><input type="file" name="file"> <button>Ответить</button></p></form>
{% else %}<div class="gate">Писать ответы могут только зарегистрированные. <a href="/login">Войти через Google</a></div>{% endif %}{% endblock %}"""

ADMIN = """{% extends "base.html" %}{% block c %}<h1>Админка</h1><div class="mut">Тем всего: {{n}}. Админов назначает только owner.</div>
<div class="card"><table><tr><th>Ник</th><th>Email</th><th>Роль</th><th>Подпись</th><th>Бан</th><th></th></tr>
{% for u in users %}<tr><form method="post" action="/admin/user"><input type="hidden" name="_csrf" value="{{csrf()}}"><input type="hidden" name="id" value="{{u.id}}">
<td class="n {{u.role}}">{{u.name}}</td><td class="mut">{{u.email}}</td>
<td><select name="role">{% for k,v in ROLES.items() %}<option value="{{k}}" {% if k==u.role %}selected{% endif %}>{{v}}</option>{% endfor %}</select></td>
<td><input type="text" name="title" value="{{u.title}}" maxlength="24" placeholder="по умолчанию"></td>
<td><input type="checkbox" name="banned" {% if u.banned %}checked{% endif %}></td><td><button>OK</button></td></form></tr>{% endfor %}</table></div>
<h1>Разделы</h1><div class="card">{% for c in cats %}<div class="row"><div class="m">{{c.name}} {% if c.staff_only %}<span class="mut">(только персонал)</span>{% endif %}</div>
<form method="post" action="/admin/cat/{{c.id}}/delete" onsubmit="return confirm('Удалить раздел со всеми темами?')"><input type="hidden" name="_csrf" value="{{csrf()}}"><button class="ghost">Удалить</button></form></div>{% endfor %}</div>
<form method="post" action="/admin/cat" class="card" style="padding:14px"><input type="hidden" name="_csrf" value="{{csrf()}}">
<input type="text" name="name" placeholder="Название раздела" required><input type="text" name="descr" placeholder="Описание" style="margin-top:8px">
<p><label><input type="checkbox" name="staff_only"> только персонал пишет</label> <button>Добавить</button></p></form>{% endblock %}"""

TEMPLATES = {"base.html": BASE, "index.html": INDEX, "cat.html": CAT, "topic.html": TOPIC, "admin.html": ADMIN}
