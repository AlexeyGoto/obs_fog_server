# OBS Fog Server - Deployment Guide

Подробная инструкция по локальному тестированию и развёртыванию на VPS.

---

## Оглавление

1. [Локальное тестовое развёртывание](#локальное-тестовое-развёртывание)
2. [Развёртывание на VPS](#развёртывание-на-vps)
3. [Настройка Telegram бота](#настройка-telegram-бота)
4. [Troubleshooting](#troubleshooting)

---

## Локальное тестовое развёртывание

### Требования

- Docker Desktop (Windows/Mac) или Docker + Docker Compose (Linux)
- Git
- Минимум 4GB RAM
- Порты: 5432, 6379, 8000, 8080, 1935 должны быть свободны

### Шаг 1: Клонирование и настройка

```bash
# Клонировать репозиторий
git clone https://github.com/your-repo/obs-fog-server.git
cd obs-fog-server

# Создать .env файл (опционально для локального тестирования)
cp .env.example .env.local
```

### Шаг 2: Настройка .env.local (опционально)

Для локального тестирования можно не менять ничего. Если хотите подключить Telegram бота:

```env
# .env.local

# Telegram бот (опционально)
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_ADMIN_ID=123456789
```

**Как получить TELEGRAM_BOT_TOKEN:**
1. Откройте [@BotFather](https://t.me/BotFather) в Telegram
2. Отправьте `/newbot`
3. Укажите имя и username для бота
4. Скопируйте токен (формат: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

**Как получить TELEGRAM_ADMIN_ID:**
1. Откройте [@userinfobot](https://t.me/userinfobot) в Telegram
2. Отправьте `/start`
3. Скопируйте ваш ID (числовой)

### Шаг 3: Создание директорий для данных

```bash
# Windows (PowerShell)
New-Item -ItemType Directory -Force -Path data/hls, data/videos

# Linux/Mac
mkdir -p data/hls data/videos
```

### Шаг 4: Запуск

```bash
# Сборка и запуск всех сервисов
docker compose -f docker-compose.dev.yml up --build

# Или в фоновом режиме
docker compose -f docker-compose.dev.yml up --build -d

# Просмотр логов
docker compose -f docker-compose.dev.yml logs -f
```

### Шаг 5: Проверка

После запуска (подождите 30-60 секунд для инициализации):

| Сервис | URL | Описание |
|--------|-----|----------|
| Web UI | http://localhost:8080 | Основной интерфейс |
| API Docs | http://localhost:8000/docs | Swagger документация |
| Health Check | http://localhost:8000/healthz | Статус API |
| RTMP Stats | http://localhost:8080/stat | Статистика RTMP |

**Тестирование регистрации:**
1. Откройте http://localhost:8080/register
2. Создайте аккаунт (email + пароль)
3. Войдите на http://localhost:8080/login
4. Перейдите на Dashboard

### Шаг 6: Остановка

```bash
# Остановить сервисы
docker compose -f docker-compose.dev.yml down

# Остановить и удалить данные (включая БД)
docker compose -f docker-compose.dev.yml down -v
```

### Тестирование стриминга (OBS)

1. В дашборде создайте PC (Add New PC)
2. Скопируйте Stream Key
3. В OBS Studio:
   - Settings → Stream
   - Service: Custom
   - Server: `rtmp://localhost:1935/live`
   - Stream Key: (вставьте скопированный ключ)
4. Start Streaming
5. В дашборде должен появиться статус "LIVE"

---

## Развёртывание на VPS

### Требования к серверу

- Ubuntu 22.04 LTS (рекомендуется) или Debian 12
- Минимум 2 vCPU, 4GB RAM, 40GB SSD
- Публичный IP адрес
- Открытые порты: 22 (SSH), 80, 443, 1935 (RTMP)
- Доменное имя (для HTTPS)

### Шаг 1: Подключение к серверу

```bash
ssh root@YOUR_SERVER_IP
```

### Шаг 2: Установка Docker

```bash
# Обновление системы
apt update && apt upgrade -y

# Установка Docker
curl -fsSL https://get.docker.com | sh

# Добавление пользователя в группу docker (опционально)
usermod -aG docker $USER

# Установка Docker Compose plugin
apt install docker-compose-plugin -y

# Проверка
docker --version
docker compose version
```

### Шаг 3: Настройка файрвола

```bash
# Установка ufw если его нет
apt install ufw -y

# Базовые правила
ufw default deny incoming
ufw default allow outgoing

# SSH (ВАЖНО: не забудьте!)
ufw allow 22/tcp

# HTTP/HTTPS
ufw allow 80/tcp
ufw allow 443/tcp

# RTMP для стриминга
ufw allow 1935/tcp

# Включение файрвола
ufw enable

# Проверка
ufw status
```

### Шаг 4: Клонирование проекта

```bash
# Создание директории
mkdir -p /opt
cd /opt

# Клонирование
git clone https://github.com/your-repo/obs-fog-server.git
cd obs-fog-server

# Создание директорий для данных
mkdir -p data/hls data/videos
```

### Шаг 5: Настройка .env

```bash
# Копирование шаблона
cp .env.example .env

# Редактирование
nano .env
```

**Заполните .env файл:**

```env
# ===== ОБЯЗАТЕЛЬНЫЕ НАСТРОЙКИ =====

# База данных PostgreSQL
POSTGRES_USER=obsfog
POSTGRES_PASSWORD=СГЕНЕРИРУЙТЕ_СЛОЖНЫЙ_ПАРОЛЬ_32_СИМВОЛА
POSTGRES_DB=obsfog
DATABASE_URL=postgresql+asyncpg://obsfog:СГЕНЕРИРУЙТЕ_СЛОЖНЫЙ_ПАРОЛЬ_32_СИМВОЛА@postgres:5432/obsfog

# JWT секрет (ОБЯЗАТЕЛЬНО ИЗМЕНИТЕ!)
# Сгенерировать: openssl rand -hex 64
JWT_SECRET=СГЕНЕРИРУЙТЕ_СЕКРЕТ_128_СИМВОЛОВ_С_ПОМОЩЬЮ_OPENSSL

# Публичный URL вашего сервера
APP_BASE_URL=https://your-domain.com

# ===== TELEGRAM (рекомендуется) =====

# Токен от @BotFather
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz

# Ваш Telegram ID для получения уведомлений админа
TELEGRAM_ADMIN_ID=123456789

# Требовать одобрения новых пользователей?
APPROVAL_REQUIRED=true

# ===== ДОПОЛНИТЕЛЬНЫЕ НАСТРОЙКИ =====

# Окружение
ENVIRONMENT=production
DEBUG=false

# Rate limiting
RATE_LIMIT_REQUESTS=100
RATE_LIMIT_WINDOW_SECONDS=60

# HLS настройки
HLS_BASE_URL=https://your-domain.com/hls

# Premium (если используете платежи)
PREMIUM_PRICE_USDT=10.0
PREMIUM_DURATION_DAYS=30
```

**Генерация секретов:**

```bash
# JWT Secret (128 символов hex)
openssl rand -hex 64

# Пароль базы данных (32 символа)
openssl rand -base64 32 | tr -d '/+=' | head -c 32
```

### Шаг 6: Настройка docker-compose.yml для production

```bash
# Создайте или отредактируйте docker-compose.yml
nano docker-compose.yml
```

```yaml
# docker-compose.yml для production

services:
  postgres:
    image: postgres:16-alpine
    container_name: obsfog_postgres
    restart: always
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: obsfog_redis
    restart: always
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  api:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: obsfog_api
    restart: always
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - REDIS_URL=redis://redis:6379/0
      - JWT_SECRET=${JWT_SECRET}
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
      - TELEGRAM_ADMIN_ID=${TELEGRAM_ADMIN_ID}
      - APP_BASE_URL=${APP_BASE_URL}
      - HLS_BASE_URL=${HLS_BASE_URL}
      - ENVIRONMENT=production
      - DEBUG=false
      - APPROVAL_REQUIRED=${APPROVAL_REQUIRED:-true}
    volumes:
      - ./data/videos:/data/videos

  worker:
    build:
      context: .
      dockerfile: worker_service/Dockerfile
    container_name: obsfog_worker
    restart: always
    depends_on:
      - postgres
      - api
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
      - HLS_BASE_URL=http://nginx:8080/hls
    volumes:
      - ./data/videos:/data/videos
      - ./data/hls:/data/hls:ro

  bot:
    build:
      context: .
      dockerfile: bot_service/Dockerfile
    container_name: obsfog_bot
    restart: always
    depends_on:
      - postgres
      - api
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
      - TELEGRAM_ADMIN_ID=${TELEGRAM_ADMIN_ID}
      - API_BASE_URL=http://api:8000
      - APPROVAL_REQUIRED=${APPROVAL_REQUIRED:-true}

  nginx:
    build:
      context: ./nginx
      dockerfile: Dockerfile
    container_name: obsfog_nginx
    restart: always
    depends_on:
      - api
    ports:
      - "80:8080"
      - "1935:1935"
    volumes:
      - ./data/hls:/data/hls

volumes:
  postgres_data:
```

### Шаг 7: Сборка и запуск

```bash
# Сборка образов
docker compose build

# Запуск в фоновом режиме
docker compose up -d

# Просмотр логов
docker compose logs -f

# Проверка статуса
docker compose ps
```

### Шаг 8: Применение миграций

```bash
# Выполнение миграций БД
docker compose exec api alembic upgrade head
```

### Шаг 9: Настройка HTTPS (рекомендуется)

**Вариант A: Certbot + внешний Nginx**

```bash
# Установка certbot
apt install certbot python3-certbot-nginx -y

# Установка nginx на хосте
apt install nginx -y

# Создание конфигурации
nano /etc/nginx/sites-available/obsfog
```

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;

    location / {
        proxy_pass http://127.0.0.1:80;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    location /hls/ {
        proxy_pass http://127.0.0.1:80/hls/;
        add_header Cache-Control "no-cache";
    }
}
```

```bash
# Активация сайта
ln -s /etc/nginx/sites-available/obsfog /etc/nginx/sites-enabled/

# Получение сертификата
certbot --nginx -d your-domain.com

# Проверка и перезагрузка
nginx -t && systemctl reload nginx
```

### Шаг 10: Настройка автозапуска

```bash
# Создание systemd service
nano /etc/systemd/system/obsfog.service
```

```ini
[Unit]
Description=OBS Fog Server
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/obs-fog-server
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
```

```bash
# Включение автозапуска
systemctl daemon-reload
systemctl enable obsfog
systemctl start obsfog

# Проверка статуса
systemctl status obsfog
```

---

## Настройка Telegram бота

### Создание бота

1. Откройте [@BotFather](https://t.me/BotFather)
2. Отправьте `/newbot`
3. Введите имя бота (например: "OBS Fog Notifications")
4. Введите username (например: "obsfog_notify_bot")
5. Скопируйте токен

### Настройка команд бота

В BotFather отправьте `/setcommands` и выберите вашего бота, затем отправьте:

```
start - Показать информацию
link - Привязать аккаунт по email
status - Проверить статус аккаунта
unlink - Отвязать Telegram
help - Помощь
```

### Настройка описания

В BotFather:
- `/setdescription` - краткое описание бота
- `/setabouttext` - "О боте"

---

## Troubleshooting

### Контейнер bot падает с ошибкой ModuleNotFoundError

```bash
# Пересоберите образ бота
docker compose build bot --no-cache
docker compose up -d bot
```

### База данных не подключается

```bash
# Проверьте логи postgres
docker compose logs postgres

# Проверьте переменные окружения
docker compose exec api env | grep DATABASE

# Попробуйте подключиться вручную
docker compose exec postgres psql -U obsfog -d obsfog
```

### Сайт не открывается на localhost:8080

```bash
# Проверьте что все контейнеры запущены
docker compose ps

# Проверьте логи nginx
docker compose logs nginx

# Проверьте логи api
docker compose logs api
```

### RTMP стрим не работает

1. Проверьте что порт 1935 открыт: `telnet localhost 1935`
2. Проверьте логи nginx: `docker compose logs nginx`
3. Убедитесь что stream key правильный
4. Проверьте hook endpoint: `curl http://localhost:8000/hook/on_publish`

### Очистка и полный перезапуск

```bash
# Остановить все сервисы
docker compose down

# Удалить все контейнеры и volumes
docker compose down -v

# Удалить образы
docker compose down --rmi all

# Пересобрать с нуля
docker compose build --no-cache
docker compose up -d
```

### Просмотр логов конкретного сервиса

```bash
# API
docker compose logs -f api

# Bot
docker compose logs -f bot

# Worker
docker compose logs -f worker

# Nginx
docker compose logs -f nginx

# Все сервисы
docker compose logs -f
```

### Выполнение команд внутри контейнера

```bash
# Bash в api контейнере
docker compose exec api bash

# Python shell с приложением
docker compose exec api python -c "from app.main import app; print('OK')"

# Проверка миграций
docker compose exec api alembic history
```

---

## Резервное копирование

### База данных

```bash
# Создание бэкапа
docker compose exec postgres pg_dump -U obsfog obsfog > backup_$(date +%Y%m%d).sql

# Восстановление
docker compose exec -T postgres psql -U obsfog obsfog < backup_20240101.sql
```

### Видео клипы

```bash
# Архивирование
tar -czvf videos_backup_$(date +%Y%m%d).tar.gz data/videos/
```

---

## Обновление

```bash
cd /opt/obs-fog-server

# Получить обновления
git pull origin main

# Пересобрать образы
docker compose build

# Применить миграции
docker compose exec api alembic upgrade head

# Перезапустить
docker compose up -d
```
