# Playto Payout Engine

Payout engine for Indian merchants to withdraw international payment collections to their bank accounts.

## Stack

- **Backend:** Django + DRF, PostgreSQL, Celery + Redis
- **Frontend:** React + Vite
- **Deploy:** Railway (Gunicorn + WhiteNoise)

## Local Setup

```bash
# Backend
pip install -r requirements.txt
python manage.py migrate
python manage.py seed

# Start Redis (needed for Celery)
redis-server

# Start Celery worker + beat
celery -A payout_engine worker -l info &
celery -A payout_engine beat -l info &

# Start Django
python manage.py runserver

# Frontend (separate terminal)
cd frontend && npm install && npm run dev
```

Dashboard runs at `http://localhost:3000`, API at `http://localhost:8000/api/v1/`.

## Seeded Merchants

| Merchant | ID | Balance |
|---|---|---|
| Acme Freelance | `00000000-...-000000000001` | ₹82,500 |
| Global Agency India | `00000000-...-000000000002` | ₹2,30,000 |
| Dev Studio Tech | `00000000-...-000000000003` | ₹18,500 |

Switch between merchants using the dropdown in the top-right corner.

## Deploy to Railway

1. Push to GitHub
2. Create new project on [railway.app](https://railway.app)
3. Add **PostgreSQL** and **Redis** plugins
4. Connect your GitHub repo
5. Set build command: `bash build.sh`
6. Set start command: `gunicorn payout_engine.wsgi --bind 0.0.0.0:$PORT`
7. Add a separate service for the Celery worker: `celery -A payout_engine worker -l info`

Railway auto-sets `DATABASE_URL` and `REDIS_URL`.

## API Endpoints

```
POST   /api/v1/payouts                        — Create payout (requires Idempotency-Key header)
GET    /api/v1/merchants/{id}/balance          — Get merchant balance
GET    /api/v1/merchants/{id}/payouts          — List payouts
GET    /api/v1/merchants/{id}/ledger           — List ledger entries
```

## Tests

```bash
python manage.py test core -v2
```

Covers: balance calculation, idempotency (hash, replay, conflict, expiry), concurrent double-spend prevention, state machine transitions.
