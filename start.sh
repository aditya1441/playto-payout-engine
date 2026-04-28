#!/bin/bash
set -e
python manage.py migrate
python manage.py seed

# Start Celery worker in background
celery -A payout_engine worker -l info --concurrency=2 &

# Start web server in foreground
gunicorn payout_engine.wsgi --bind 0.0.0.0:$PORT --workers 2
