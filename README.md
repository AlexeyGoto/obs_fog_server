# OBS Fog Server v2.0

Modern FastAPI-based streaming management platform for OBS streamers.

## Features

- **User Authentication**: JWT-based auth with registration, login, password reset
- **Role-Based Access**: User, Premium, Admin roles
- **PC Management**: Add multiple streaming PCs, manage stream keys
- **RTMP Streaming**: nginx-rtmp integration for live streaming
- **Automatic Clips**: Records last 7 minutes of each stream as MP4
- **Telegram Integration**: Bot for account linking, notifications, admin approvals
- **Premium Payments**: Telegram Wallet USDT payments for premium subscriptions
- **SteamSlot**: Account slot management for streamers
- **Modern UI**: Responsive dashboard with Tailwind CSS

## Tech Stack

- **Backend**: FastAPI (async), SQLAlchemy 2.0 (async), PostgreSQL
- **Auth**: JWT tokens, bcrypt password hashing
- **Streaming**: nginx-rtmp, HLS
- **Queue**: Redis (rate limiting, caching)
- **Frontend**: Jinja2, Tailwind CSS, Alpine.js
- **DevOps**: Docker, Docker Compose, Alembic migrations

---

## Quick Start

> **Подробная инструкция по развёртыванию:** см. [DEPLOYMENT.md](DEPLOYMENT.md)

### Prerequisites

- Docker and Docker Compose
- PostgreSQL (or use the included Docker container)
- Telegram Bot (for notifications)

### 1. Clone and Configure

```bash
git clone https://github.com/your-repo/obs-fog-server.git
cd obs-fog-server

# Copy environment template
cp .env.example .env

# Edit configuration
nano .env
```

**Required settings in `.env`:**

```env
# Generate a secure secret
JWT_SECRET=$(openssl rand -hex 64)

# Database
POSTGRES_USER=obsfog
POSTGRES_PASSWORD=your_secure_password
POSTGRES_DB=obsfog

# Telegram (optional but recommended)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_ADMIN_ID=your_telegram_id

# Public URL
APP_BASE_URL=http://your-server:8080
```

### 2. Start with Docker

```bash
# Development mode (with hot reload)
docker compose -f docker-compose.dev.yml up

# Production mode
docker compose up -d --build
```

### 3. Run Migrations

```bash
# Inside the container or with alembic installed locally
docker compose exec api alembic upgrade head
```

### 4. Access the Application

- **Web UI**: http://localhost:8080
- **API Docs** (dev only): http://localhost:8000/docs
- **RTMP Stats**: http://localhost:8080/stat

---

## Local Development

### Without Docker

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/macOS
# or: .\venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Set up environment
export DATABASE_URL=postgresql+asyncpg://obsfog:password@localhost:5432/obsfog_dev
export JWT_SECRET=dev_secret_key
export DEBUG=true

# Run migrations
alembic upgrade head

# Start the server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Running Tests

```bash
# Install test dependencies (included in requirements.txt)
pip install pytest pytest-asyncio pytest-cov httpx aiosqlite

# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/test_auth.py -v
```

---

## API Endpoints

### Authentication

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/auth/register` | POST | Register new user |
| `/api/v1/auth/login` | POST | Login, get JWT tokens |
| `/api/v1/auth/logout` | POST | Logout, clear session |
| `/api/v1/auth/refresh` | POST | Refresh access token |
| `/api/v1/auth/password` | POST | Change password |
| `/api/v1/auth/me` | GET | Get current user |

### PCs

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/pcs` | GET | List user's PCs |
| `/api/v1/pcs` | POST | Create new PC |
| `/api/v1/pcs/{id}` | GET | Get PC details |
| `/api/v1/pcs/{id}` | PATCH | Update PC |
| `/api/v1/pcs/{id}` | DELETE | Delete PC |
| `/api/v1/pcs/{id}/regenerate-key` | POST | New stream key |
| `/api/v1/pcs/{id}/sessions` | GET | List sessions |

### Downloads

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/downloads/obs-profile/{id}` | GET | Download OBS profile ZIP |
| `/api/v1/downloads/steamslot-script/{id}` | GET | Download PS1 script |
| `/api/v1/downloads/obs-installer/{id}` | GET | Download installer script |

### Payments

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/payments/create-invoice` | POST | Create Telegram Wallet invoice |
| `/api/v1/payments` | GET | List user payments |
| `/api/v1/payments/premium/status` | GET | Check premium status |

---

## OBS Configuration

### Manual Setup

1. Open OBS Studio
2. Go to Settings → Stream
3. Set Service to "Custom"
4. Enter:
   - **Server**: `rtmp://your-server-ip:1935/live`
   - **Stream Key**: (copy from dashboard)

### Automatic Setup

1. Go to your dashboard
2. Click on your PC → "Download OBS Profile"
3. Extract to `%APPDATA%\obs-studio\basic\profiles\`
4. Restart OBS and select the profile

---

## Telegram Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Show bot info and your chat ID |
| `/link <email>` | Link your account |
| `/status` | Check account status |
| `/unlink` | Unlink Telegram |

### Admin Commands (inline buttons)

- When a user registers with `APPROVAL_REQUIRED=true`, admin receives approval buttons
- "✅ Approve" / "⛔ Deny" to manage user registrations

---

## Premium Payments (Telegram Wallet)

OBS Fog Server supports payments via Telegram Wallet with USDT on TON network.

### Setup

1. Contact @BotFather and enable payments for your bot
2. Get provider token for Telegram Wallet
3. Set in `.env`:
   ```env
   TELEGRAM_WALLET_TOKEN=your_provider_token
   PREMIUM_PRICE_USDT=10.0
   PREMIUM_DURATION_DAYS=30
   ```

### Payment Flow

1. User clicks "Upgrade to Premium" in profile
2. API creates invoice via Telegram Bot API
3. User opens invoice link in Telegram
4. User completes payment with Telegram Wallet
5. Webhook confirms payment, activates premium

---

## Deployment to VPS

### Using Docker (Recommended)

```bash
# On your VPS
ssh root@your-server

# Install Docker
curl -fsSL https://get.docker.com | sh

# Clone and setup
git clone https://github.com/your-repo/obs-fog-server.git
cd obs-fog-server
cp .env.example .env
nano .env  # Configure settings

# Create directories
mkdir -p data/hls data/videos

# Open ports
ufw allow 1935/tcp  # RTMP
ufw allow 8080/tcp  # HTTP
ufw reload

# Start
docker compose up -d --build

# Check logs
docker compose logs -f
```

### Using systemd

Create `/etc/systemd/system/obsfog.service`:

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

Enable and start:

```bash
systemctl daemon-reload
systemctl enable obsfog
systemctl start obsfog
```

### With HTTPS (Nginx Reverse Proxy)

```nginx
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /hls/ {
        proxy_pass http://127.0.0.1:8080/hls/;
        add_header Cache-Control no-cache;
    }
}
```

---

## Project Structure

```
obs-fog-server/
├── app/
│   ├── core/           # Config, database, security, dependencies
│   ├── models/         # SQLAlchemy models
│   ├── schemas/        # Pydantic schemas
│   ├── routers/        # FastAPI route handlers
│   ├── services/       # Business logic services
│   ├── static/         # CSS, JS assets
│   │   ├── css/app.css
│   │   └── js/app.js
│   ├── templates/      # Jinja2 HTML templates
│   │   ├── auth/       # Login, register
│   │   ├── pages/      # Dashboard, profile, etc.
│   │   ├── admin/      # Admin panel
│   │   └── base.html   # Base template
│   └── main.py         # FastAPI app factory
├── alembic/            # Database migrations
├── bot_service/        # Telegram bot
├── worker_service/     # Background worker
├── tests/              # Pytest tests
├── scripts/            # Utility scripts
├── docker-compose.yml  # Production Docker setup
└── requirements.txt    # Python dependencies
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    NGINX (RTMP + HTTP)                       │
│                    Ports: 1935, 8080                         │
├─────────────────────────────────────────────────────────────┤
│  RTMP:                                                       │
│  - Receives OBS streams                                      │
│  - Converts to HLS (m3u8 + ts)                              │
│  - Calls webhook on publish/done                             │
├─────────────────────────────────────────────────────────────┤
│  HTTP:                                                       │
│  - Serves HLS at /hls/                                       │
│  - Proxies API at /api/                                      │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                        API (FastAPI)                         │
│                        Port: 8000                            │
├─────────────────────────────────────────────────────────────┤
│  - JWT Authentication                                        │
│  - User/PC/Session management                                │
│  - RTMP hooks (on_publish, on_publish_done)                  │
│  - Payment processing                                        │
│  - File downloads                                            │
└───────────────────────────┬─────────────────────────────────┘
                            │
                ┌───────────┴───────────┐
                │                       │
┌───────────────▼──────┐  ┌────────────▼────────────┐
│  PostgreSQL          │  │  Redis                  │
│  - Users             │  │  - Rate limiting        │
│  - PCs               │  │  - Session cache        │
│  - Sessions          │  │                         │
│  - Payments          │  │                         │
└──────────────────────┘  └─────────────────────────┘

┌──────────────────────┐  ┌─────────────────────────┐
│  Worker              │  │  Telegram Bot           │
│  - Clip creation     │  │  - User linking         │
│  - HLS → MP4         │  │  - Admin approvals      │
│  - Telegram send     │  │  - Notifications        │
└──────────────────────┘  └─────────────────────────┘
```

---

## Troubleshooting

### Stream not appearing in HLS

1. Check if user is approved: `APPROVAL_REQUIRED=true` blocks unapproved users
2. Check nginx logs: `docker compose logs nginx`
3. Check API logs: `docker compose logs api`
4. Verify stream key is correct

### 429 Rate Limit Errors

Rate limiting is set to 100 requests per minute by default. Adjust in `.env`:

```env
RATE_LIMIT_REQUESTS=200
RATE_LIMIT_WINDOW_SECONDS=60
```

### Database Connection Issues

If using remote PostgreSQL, ensure connection string is properly URL-encoded:

```env
DATABASE_URL=postgresql+asyncpg://user:p%40ssword@host:5432/db
```

### Telegram Bot Not Working

1. Verify `TELEGRAM_BOT_TOKEN` is correct
2. Check bot is not blocked by user
3. For webhooks, ensure public URL is accessible

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Make changes and test
4. Commit: `git commit -m 'Add amazing feature'`
5. Push: `git push origin feature/amazing-feature`
6. Open a Pull Request

---

## License

MIT License - see LICENSE file for details.

---

## Support

- GitHub Issues: Report bugs and feature requests
- Telegram: @your_support_channel
