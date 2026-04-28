#!/bin/bash
set -e
python manage.py migrate
python manage.py seed
gunicorn payout_engine.wsgi --bind 0.0.0.0:$PORT --workers 3
