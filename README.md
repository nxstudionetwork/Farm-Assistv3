# Farm Assist - Full Stack Application

A comprehensive farm management platform with a Python FastAPI backend, SQLite/PostgreSQL database, and existing HTML/CSS/JS frontend.

## Quick Start

```bash
# 1. Install Python dependencies
cd backend
pip install -r requirements.txt

# 2. Set up environment
copy .env.example .env

# 3. Apply database migrations
python -m alembic upgrade head

# 4. Seed test data
python seed.py

# 5. Start the server
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open **http://localhost:8000** for the app, or **http://localhost:8000/docs** for Swagger API docs.

**On your local network** (server binds `0.0.0.0`), open **http://192.168.16.56:8000** from any device on the same Wi-Fi/LAN. To find your IP: `ipconfig` (IPv4 address) or `Get-NetIPAddress`. If your IP changes, replace `192.168.16.56` and add it to `CORS_ORIGINS` in `backend/.env`.

**Test credentials:** Phone `9876543210`, PIN/Password `1234`

## Architecture

```
Farm_Assist.Application/
├── frontend/                     # Existing HTML/CSS/JS (44 pages)
├── backend/
│   ├── app/
│   │   ├── main.py               # FastAPI entry point
│   │   ├── config.py             # Environment settings
│   │   ├── database/             # SQLAlchemy engine + Alembic migrations
│   │   ├── models/               # 13 model files (30+ tables)
│   │   ├── schemas/              # 11 Pydantic schema files
│   │   ├── routers/              # 13 API routers
│   │   ├── services/             # Weather, AI, Maps, Notifications
│   │   └── utils/                # Auth, exceptions
│   ├── tests/                    # API tests (24 passing)
│   ├── alembic.ini               # Migration config
│   ├── seed.py                   # Database seeder
│   ├── requirements.txt          # Python dependencies
│   └── .env.example              # Environment template
```

## API Endpoints

| Module     | Base Path           | Endpoints                                           |
|------------|---------------------|-----------------------------------------------------|
| Auth       | `/api/v1/`          | register, login, logout, send-otp, verify-otp, /me  |
| Users      | `/api/v1/users`     | profile GET/PUT, address PUT                        |
| Farms      | `/api/v1/farms`     | CRUD + nested plots CRUD                            |
| Crops      | `/api/v1/crops`     | catalog, cycles, tasks, journal                     |
| Finance    | `/api/v1/`          | summary, transactions, expenses, income             |
| Workers    | `/api/v1/workers`   | list, detail, bookings CRUD                         |
| Marketplace| `/api/v1/marketplace`| products, categories, orders CRUD                   |
| Government | `/api/v1/government`| schemes, applications, insurance policies/claims    |
| Community  | `/api/v1/`          | posts, comments, likes, experts, consultations      |
| Notifications| `/api/v1/notifications`| list, mark read, unread count                   |
| Weather    | `/api/v1/weather`   | current + forecast (Open-Meteo)                     |
| Maps       | `/api/v1/maps`      | geocode + reverse geocode (Nominatim)               |
| AI         | `/api/v1/ai`        | chat, recommendations, farm analysis, diagnosis      |

## Features

- **JWT Authentication** with password hashing and OTP support
- **Auto-generated IDs** (FA-FRM-000001, FA-FARM-000001, FA-PLT-000001, etc.)
- **Financial tracking** with income, expenses, net profit, monthly trends
- **Weather integration** via Open-Meteo API (free, no key required)
- **AI Assistant** with OpenAI/Gemini/Claude integration + intelligent local fallback
- **Geocoding** via Nominatim (free, no key required)
- **Frontend served** from the same server at root path

## Database

- **Dev:** SQLite (`farm_assist.db`)
- **Prod:** Set `DATABASE_URL` in `.env` to PostgreSQL connection string
- **Migrations:** Alembic (`python -m alembic upgrade head`)

## Environment Variables

Copy `.env.example` to `.env` and fill in:

| Variable          | Required | Default                | Description                 |
|-------------------|----------|------------------------|-----------------------------|
| SECRET_KEY        | Yes      | (auto-generated)       | JWT secret                  |
| DATABASE_URL      | No       | sqlite:///./farm_assist.db | Database connection      |
| OPENAI_API_KEY    | No       | -                      | OpenAI API key              |
| GEMINI_API_KEY    | No       | -                      | Google Gemini API key       |
| ANTHROPIC_API_KEY | No       | -                      | Anthropic Claude API key    |

AI works without any API keys using intelligent local fallback responses.

## Running Tests

```bash
cd backend
python -m pytest tests/test_api.py -v
```

24 tests covering auth, farms, crops, finance, workers, marketplace, government, community, notifications, weather, and AI.
