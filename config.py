# config.py
import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'cok-gizli-bir-anahtar'

    # --- Merkezi Dosya Yükleme Ayarları (Orijinal Mantıktan Alındı) ---
    UPLOAD_FOLDER = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'uploads')
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf', 'xlsx', 'xls', 'csv'}
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024

    # --- Veritabanı Bağlantı Ayarları (Güncel) ---
    DATABASE_URL = os.environ.get("DATABASE_URL")
    if DATABASE_URL:
        SQLALCHEMY_DATABASE_URI = DATABASE_URL
        SQLALCHEMY_ENGINE_OPTIONS = {
            'connect_args': {
                "ssl_verify_cert": False
            }
        }
    else:
        print("UYARI: Harici veritabanı için 'DATABASE_URL' gizli anahtarı bulunamadı.")
        SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(os.path.abspath(os.path.dirname(__file__)), 'hr.db')

    SQLALCHEMY_TRACK_MODIFICATIONS = False
