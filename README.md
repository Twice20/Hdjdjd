# Форум + Telegram-деплой-бот

## Запуск на bothost.ru
1. Создайте бота в @BotFather, получите токен.
2. Загрузите содержимое этой папки (bot.py, requirements.txt, папка site/) на хостинг.
3. Переменная окружения `BOT_TOKEN`; команда запуска `python bot.py`.
4. Напишите боту (только ваш ID 8171375787 получит ответ):
   - `/set GOOGLE_CLIENT_ID ...`, `/set GOOGLE_CLIENT_SECRET ...`, `/set OWNER_EMAIL вашапочта@gmail.com`
   - `/domain forum.example.com` — домен меняется в любой момент
5. Google Cloud Console → Credentials → OAuth client (Web) → Authorized redirect URI: `https://ваш-домен/auth/callback`
6. Первый вход с OWNER_EMAIL автоматически даёт роль OWNER, дальше админов назначаете в /admin.

Обновление сайта: отправьте боту zip (app.py в корне). data/ (база, загрузки) сохраняется. /rollback — откат.
