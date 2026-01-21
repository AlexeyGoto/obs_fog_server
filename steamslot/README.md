# Steam Login Slot Service (Timeweb Apps / Dockerfile)

Сервис «слотов» для безопасной раздачи `loginusers.vdf` (не более N одновременных логинов на один Steam-аккаунт).

## Как подключить БД Timeweb (как на скрине .env)
Код умеет:
- брать `DATABASE_URL` (если задан),
- или собирать строку подключения из переменных:
  `POSTGRESQL_HOST`, `POSTGRESQL_PORT`, `POSTGRESQL_USER`, `POSTGRESQL_PASSWORD`, `POSTGRESQL_DBNAME`,
  а также (опционально) `POSTGRESQL_SSLMODE`, `POSTGRESQL_SSLROOTCERT`.

## Переменные окружения (минимум)
- ADMIN_USER
- ADMIN_PASS
- (БД) DATABASE_URL **или** POSTGRESQL_*

Опционально:
- FILE_ENC_KEY — Fernet-ключ для шифрования файла в БД
- REQUIRE_PC_KEY=1

Сгенерированные значения (переопределите в проде):
- ADMIN_USER=admin
- ADMIN_PASS=Admin-kFnwZmGm_oQfLyrP
- MASTER_API_KEY=Master-yc4zpxA1gZycDFJj4JSJWGry
- FILE_ENC_KEY=IWhnayc83AAbfPiiBgdcucWZX6OAct-UK3SHvsV9eC8=

## Локальный запуск
1) `python -m venv .venv`
2) `.venv\Scripts\activate`
3) `pip install -r requirements.txt`
4) Создайте `.env` по примеру из панели Timeweb и запустите:
   `powershell -ExecutionPolicy Bypass -File .\run_local.ps1`

## ВАЖНО про ошибку ImportError (relative import)
Не запускайте `python app\main.py`.
Запускайте так:
- `python -m uvicorn app.main:app --reload --port 8080`
или
- `powershell -File .\run_local.ps1`
