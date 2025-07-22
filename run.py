# run.py
# Bu dosya, Gunicorn'un çalıştıracağı Flask 'app' nesnesini sağlar.

import sys
import os

# 'app' klasörünü bulabilmek için projenin ana dizinini Python yoluna ekle.
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app import create_app

app = create_app()
