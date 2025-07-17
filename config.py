import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'cok-gizli-ve-guvenli-bir-anahtar')
    DATABASE = 'hr.db'
    UPLOAD_FOLDER = 'uploads'
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}