#!/bin/bash
set -e

# Install Python deps
pip install -r requirements.txt

# Build React frontend
cd frontend
npm install
npm run build
cd ..

# Collect static files
python manage.py collectstatic --noinput

# Run migrations
python manage.py migrate

# Seed data
python manage.py seed
