# OBS Fog Service v2 (RTMP → HLS → последние 7 минут → Telegram)

Сервис для **80+ ПК**:
- OBS на каждом ПК стримит по RTMP на VPS.
- NGINX-RTMP генерирует HLS и держит «скользящее окно» последних ~7 минут.
- После окончания стрима NGINX дергает hook `on_publish_done`, мы ставим задачу в очередь.
- Worker склеивает HLS → MP4 (без перекодирования, `-c copy`).
- Если файл <= лимита Telegram (по умолчанию 50 МБ) — отправляем владельцу.
- Если больше — отправляем владельцу уведомление «слишком большой файл».
- После попытки отправки (успех/ошибка/слишком большой) mp4 удаляется, если включено `auto_delete`.

## Архитектура
- `nginx` — RTMP ingest (1935) + HTTP (8080) + HLS раздача
- `api` — FastAPI: сайт, авторизация, управление ПК, hooks, bot API
- `worker` — обработка очереди: ffmpeg + Telegram sendVideo
- `bot` — Telegram бот (long polling) для команд `/pcs`, `/obs`, `/live`, `/link CODE`

## Быстрый старт (VPS)

### 1) Установка Docker (Ubuntu 22.04/24.04)
```bash
apt-get update -y
apt-get install -y ca-certificates curl gnupg
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
```

### 2) Разворачивание проекта
```bash
mkdir -p /opt/obs_fog_service
cd /opt/obs_fog_service
# сюда положи содержимое репозитория (git clone или scp)
cp .env.example .env
nano .env
```

Минимально в `.env` нужно:
- `APP_BASE_URL=http://<ваш-ip>:8080`
- `JWT_SECRET=...`
- `BOT_API_TOKEN=...`
- `TELEGRAM_BOT_TOKEN=...`
- `DATABASE_URL=sqlite:////data/db/app.db`

### 3) Старт
```bash
docker compose up -d --build
```

Открыть сайт:
- `http://<ваш-ip>:8080`

### 4) Открыть порты
- RTMP: `1935/tcp`
- Web/HLS: `8080/tcp`

## Настройка OBS (на ПК)
В OBS выбери **Custom RTMP**:
- **Server:** `rtmp://<ваш-ip>:1935/live`
- **Stream Key:** из карточки ПК на сайте.

## Telegram
1) На сайте → **Настройки** → возьми `CODE`.
2) В Telegram боте: `/link CODE`
3) Команды:
- `/pcs` — список ПК
- `/obs PC_ID` — RTMP+key
- `/live PC_ID` — ссылка на live

## Почему не подключается OBS / FFmpeg пишет Input/output error
### Проверки
На VPS:
```bash
ss -lntp | grep 1935
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/
```
Тест RTMP локально:
```bash
ffmpeg -re -f lavfi -i testsrc=size=1280x720:rate=30 -f lavfi -i sine=frequency=1000 \
  -c:v libx264 -preset veryfast -tune zerolatency -c:a aac -f flv \
  rtmp://127.0.0.1:1935/live/<STREAM_KEY>
```
Если тест идет, а OBS снаружи нет — проверь провайдера/фаервол, что порт 1935 доступен.

## Ограничение Telegram 50 МБ
Если клип больше лимита, сервис отправляет **только уведомление владельцу** и **не держит файл** (при `auto_delete=true`).

## Масштаб (80+ ПК)
- Ingest 80×500 кбит/с = ~40 Мбит/с входящего трафика (плюс накладные)
- CPU в основном тратится на disk IO и `ffmpeg -c copy` (без перекодирования)
- По RAM обычно достаточно 1–2 ГБ под сервис, но лучше 2–4 ГБ из-за кешей и пиков IO.

