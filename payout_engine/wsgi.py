import os
from pathlib import Path
from django.core.wsgi import get_wsgi_application
from whitenoise import WhiteNoise

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'payout_engine.settings')

application = get_wsgi_application()

# Serve Vite's built assets at /assets/ directly
dist_dir = Path(__file__).resolve().parent.parent / 'frontend' / 'dist'
application = WhiteNoise(application)
application.add_files(str(dist_dir), prefix='')
