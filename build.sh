#!/bin/bash
set -e

pip install -r requirements.txt

cd frontend
npm install
npm run build
cd ..

python manage.py collectstatic --noinput
