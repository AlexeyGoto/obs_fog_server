# OBS RTMP -> 7 минут -> Telegram (Docker)

Этот проект принимает **RTMP**-стримы из OBS (80+ ПК), держит **кольцевой буфер последних 7 минут** в HLS-сегментах без перекодирования и **после завершения стрима**:

- пытается собрать MP4 из последних сегментов;
- если MP4 **<= 50 МБ** — отправляет видео в Telegram боту;
- если MP4 **> 50 МБ** — отправляет **уведомление**, что файл слишком большой (и видео не отправлено).

После обработки папка сегментов удаляется, а MP4 удаляется если включено `auto_delete`.

## Порты
- `1935/tcp` — RTMP ingest (OBS)
- `8080/tcp` — HTTP шлюз: **панель управления (FastAPI)** + HLS (`/hls/...`)

## Быстрый запуск

1) Скопируй пример окружения:
```bash
cp .env.example .env
```

2) Заполни в `.env`:
- `TELEGRAM_BOT_TOKEN` — токен бота
- `TELEGRAM_ADMIN_ID` — chat id администратора
- `PUBLIC_BASE_URL` — публичный URL панели, например `http://SERVER_IP:8080`

### (Опционально) PostgreSQL вместо SQLite
По умолчанию проект использует SQLite (`./data/db/app.db`).

Если хочешь использовать внешний PostgreSQL (как у тебя) — добавь в `.env`:
- либо `DATABASE_URL=postgresql://...`
- либо набор переменных:
  - `POSTGRESQL_HOST`
  - `POSTGRESQL_PORT`
  - `POSTGRESQL_USER`
  - `POSTGRESQL_PASSWORD`
  - `POSTGRESQL_DBNAME`

Проект автоматически переключится на Postgres при наличии `DATABASE_URL` или `POSTGRESQL_HOST`.

3) Запуск:
```bash
docker compose up -d --build
```

4) Открой панель:
- `http://SERVER_IP:8080/`

## Настройка OBS на ПК
В OBS: **Settings → Stream**
- Service: Custom...
- Server: `rtmp://SERVER_IP/live`
- Stream Key: ключ, который ты получил после добавления ПК в панели (или через `/pcs` в боте)

Рекомендация (для ровных сегментов):
- Keyframe Interval: 2 сек (или Auto)

## Что умеет панель
- Добавить ПК (генерирует stream_key)
- Список ПК со статусом LIVE/OFF
- Страница ПК: RTMP URL, stream key, и live-плеер (HLS)
- Настройки:
  - `save_videos` — собирать/отправлять видео после окончания стрима
  - `auto_delete` — удалять MP4 после отправки/уведомления
  - `strict_keys` — разрешать publish только для stream_key, которые есть в базе

## Команды Telegram бота
- `/start` — помощь
- `/pcs` — список ПК
- `/pc <id>` — настройки OBS для конкретного ПК + ссылка на страницу
- `/streams` — кто сейчас LIVE
- `/savevideos on|off` — (только admin) включить/выключить отправку видео
- `/autodelete on|off` — (только admin) удалять MP4 после обработки
- `/strictkeys on|off` — (только admin) включить/выключить строгую проверку ключей

## Данные на диске
- `./data/db/app.db` — sqlite база
- `./data/hls/<stream_key>/...` — HLS сегменты (удаляются после обработки)
- `./data/out/` — временные MP4 (удаляются если `auto_delete=true`)

## Логи
```bash
docker compose logs -f api
docker compose logs -f worker
docker compose logs -f bot
docker compose logs -f nginx
```

