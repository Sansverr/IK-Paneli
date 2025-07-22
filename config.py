import os

# Replit Secrets (ortam değişkenleri) bölümünden Aiven bağlantı URL'sini al
DATABASE_URL = os.environ.get("DATABASE_URL")

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'cok-gizli-bir-anahtar'

    if DATABASE_URL:
        # Ana bağlantı dizesini olduğu gibi kullan
        SQLALCHEMY_DATABASE_URI = DATABASE_URL

        # [SSL: CERTIFICATE_VERIFY_FAILED] hatasını çözmek için son çare.
        # Sertifika doğrulamasını devre dışı bırakıyoruz.
        # Bu, bu geliştirme ortamı için kabul edilebilir bir çözümdür.
        # Üretim ortamında kesinlikle kullanılmamalıdır.
        SQLALCHEMY_ENGINE_OPTIONS = {
            'connect_args': {
                "ssl_verify_cert": False
            }
        }
    else:
        # Eğer DATABASE_URL ayarlanmamışsa, bir uyarı göster ve yerel geliştirme için
        # eski SQLite veritabanını kullanmaya devam et.
        print("UYARI: Harici veritabanı için 'DATABASE_URL' gizli anahtarı bulunamadı. SQLite kullanılıyor.")
        SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(os.path.abspath(os.path.dirname(__file__)), 'hr.db')

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Yükleme klasörü ayarı
    UPLOAD_FOLDER = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB
