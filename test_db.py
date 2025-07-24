# test_db.py
# Bu betik, veritabanı bağlantısını test eder ve içindeki ilk yönetici
# kullanıcısının bilgilerini kontrol eder.

import sys
import os

# Betiğin, 'app' klasörünü bulabilmesi için projenin ana dizinini Python yoluna ekle.
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app import create_app, db
from app.database import User, Personnel

def check_database():
    """Veritabanını kontrol eder ve admin kullanıcısını sorgular."""
    app = create_app()
    with app.app_context():
        print("--- Veritabanı Testi Başlatılıyor ---")

        try:
            # Tüm kullanıcıları sorgula
            users = User.query.all()
            print(f"Veritabanında toplam {len(users)} kullanıcı bulundu.")

            if not users:
                print("HATA: Veritabanında hiç kullanıcı bulunamadı. Lütfen 'create_admin.py' betiğini çalıştırdığınızdan emin olun.")
                return

            # Özellikle admin kullanıcısını bul
            admin_user = User.query.filter_by(role='admin').first()

            if admin_user:
                print("\n--- Yönetici Kullanıcı Bilgileri ---")
                print(f"Kullanıcı ID: {admin_user.id}")
                print(f"TC Kimlik No (Kullanıcı Adı): {admin_user.username}")
                print(f"Rol: {admin_user.role}")

                # Yöneticiye bağlı personel kaydını bul
                if admin_user.personnel:
                    admin_personnel = admin_user.personnel[0]
                    print("\n--- Yöneticiye Bağlı Personel Kaydı ---")
                    print(f"Personel ID: {admin_personnel.id}")
                    print(f"Ad: {admin_personnel.name}")
                    print(f"Soyad: {admin_personnel.surname}")
                    print(f"E-posta: {admin_personnel.email}")
                    print("---------------------------------------")
                else:
                    print("UYARI: Yönetici kullanıcısına bağlı bir personel kaydı bulunamadı.")

                print("\nTEST BAŞARILI: Veritabanı bağlantısı ve yönetici kaydı doğrulandı.")

            else:
                print("HATA: 'admin' rolüne sahip bir kullanıcı bulunamadı.")

        except Exception as e:
            print(f"Veritabanı sorgulanırken bir HATA oluştu: {e}")

if __name__ == '__main__':
    check_database()
