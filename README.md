# OBS + SteamSlot All-in-One v3

Один VPS, один nginx (RTMP + HTTP), два сервиса:
- OBS Fog Service (RTMP ingest + HLS + web UI + Telegram bot + worker)
- SteamSlot service (из `steam_update_srv`, работает под `/steamslot/`)

## Порты
- 1935/tcp — RTMP ingest (OBS)
- 8080/tcp — Web UI + HLS + SteamSlot UI

## Быстрый старт на Ubuntu 22/24

### 1) Установить Docker
```bash
apt update -y
apt install -y ca-certificates curl gnupg lsb-release tmux

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" > /etc/apt/sources.list.d/docker.list
apt update -y
apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

### 2) Открыть порты
```bash
ufw allow 1935/tcp
ufw allow 8080/tcp
ufw reload
```

### 3) Развернуть проект
```bash
cd /opt
git clone <YOUR_GIT_REPO_URL> obs_allinone_v3
cd obs_allinone_v3
cp .env.example .env
nano .env
```

### 4) Запуск устойчиво (чтобы SSH не слетал)
```bash
tmux new -s obs
```

### 5) Первый запуск — БЕЗ -d (чтобы видеть ошибки)
```bash
docker compose down --remove-orphans
mkdir -p data/hls data/db data/videos
docker compose up --build
```

Если всё ок — Ctrl+C, затем в фон:
```bash
docker compose up -d
docker compose ps
docker compose logs -f --tail=200
```

## Диагностика если билд «долго»
В отдельном окне:
```bash
ps aux | grep -E "docker compose|buildkit|apk add|make|gcc|curl|tar" | grep -v grep | head -n 30
```

Nginx собирается из исходников, но мы используем ускоренное зеркало Alpine (`mirror.yandex.ru`) и разбитые RUN-слои, чтобы не было «тишины» по 30+ минут.

## URLs
- OBS Web: `http://<VPS_IP>:8080/`
- HLS: `http://<VPS_IP>:8080/hls/live/<stream_key>/index.m3u8`
- SteamSlot: `http://<VPS_IP>:8080/steamslot/`

## OBS настройки
- Server: `rtmp://<VPS_IP>:1935/live`
- Key: `stream_key` из карточки ПК

## Telegram bot
1) Зарегистрируйся на сайте OBS.
2) В боте: `/link <email>`
3) Команды: `/pcs`, `/obs <pc_id>`, `/live <pc_id>`

## SteamSlot
SteamSlot обслуживает аренду слотов и страницы управления. Лежит под `/steamslot/`.
Для БД укажи отдельные `STEAMSLOT_...` переменные (или `STEAMSLOT_DATABASE_URL`).
