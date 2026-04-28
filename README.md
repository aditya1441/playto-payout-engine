# Playto Payout Engine

Minimal payout engine for Playto Pay. Merchants accumulate balance from international payments and withdraw to Indian bank accounts.

**Stack:** Django + DRF, PostgreSQL, Celery + Redis, React + Vite.

## Setup

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py seed
redis-server &
celery -A payout_engine worker -l info &
celery -A payout_engine beat -l info &
python manage.py runserver
cd frontend && npm install && npm run dev
```

## Tests

```bash
python manage.py test core -v2
```
