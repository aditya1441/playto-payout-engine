# Playto Payout Engine 💳

A robust, mathematically safe, and highly concurrent payout processing engine built for the Playto Founding Engineer Challenge. 

## Features
- **Idempotent Payout API:** Guaranteed exactly-once execution. Keys expire after 24 hours.
- **Race-safe Ledgers:** Double-spend prevention via `select_for_update` DB-level row locks.
- **Strict Integer Math:** All money is modeled in `paise` (BigIntegerField). No float rounding errors.
- **Atomic Background Workers:** Uses Celery with a CAS (Compare-And-Swap) queue pattern to ensure no payout is processed twice. Includes an auto-recovery beat task for stuck jobs.
- **Full Dashboard:** A modern, beautiful React + Tailwind SPA for merchants to request and track payouts in real-time.

## Tech Stack
- **Backend:** Django, Django Rest Framework, Celery, Redis, PostgreSQL (or SQLite for local dev)
- **Frontend:** React, Vite, Tailwind CSS v3
- **Testing:** Django TestCase & TransactionTestCase (Concurrent thread testing)

## Local Setup Instructions

### 1. Backend Setup
Ensure you have Python 3.10+ and Redis installed locally (`brew install redis` && `redis-server`).

```bash
# Install dependencies
pip install -r requirements.txt

# Run database migrations
python manage.py migrate

# Seed the database with 3 test merchants (with varying balances)
python manage.py shell < seed_demo.py

# Start the Django development server
python manage.py runserver
```

### 2. Start Celery Workers
In a separate terminal, start the background worker that simulates the bank gateway (70% success, 20% fail, 10% stuck timeouts):
```bash
celery -A payout_engine worker -l info
```

*(Optional)* Run the Celery Beat scheduler to automatically recover stuck payouts:
```bash
celery -A payout_engine beat -l info
```

### 3. Frontend Dashboard Setup
In a third terminal:
```bash
cd frontend
npm install
npm run dev
```

Visit `http://localhost:3000` to see the Merchant Dashboard!

## Running Tests
Run the 30 rigorous integration tests covering concurrency locks, ledger arithmetic, and idempotency states:
```bash
python manage.py test core
```
