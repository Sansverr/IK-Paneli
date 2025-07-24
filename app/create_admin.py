import os
import sys
from getpass import getpass

# Bu betiğin, 'app' klasörünü bulabilmesi için projenin ana dizinini Python yoluna ekle.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, db
from app.database import User, Personnel

def create_admin_user():
    """Yeni bir yönetici kullanıcı ve buna bağlı bir personel kaydı oluşturur."""
    app = create_app()
    with app.app_context():
        # --- Orijinal Mantık: Kullanıcıdan tüm bilgileri al ---
        ad_soyad_input = input("Adınız ve Soyadınız: ")
        tc_kimlik = input("TC Kimlik Numaranız (Giriş için): ")
        mail = input("E-posta Adresiniz (Şifre sıfırlama için): ")
        password = getpass("Oluşturmak istediğiniz şifre: ")

        # --- Orijinal Mantık: Ad ve soyadı ayır ---
        parts = ad_soyad_input.strip().split()
        soyad_str = parts[-1].title() if parts else ""
        ad_str = " ".join(parts[:-1]).title() if len(parts) > 1 else (parts[0].title() if parts else "")
        if not ad_str and soyad_str: ad_str = soyad_str; soyad_str = ""

        # --- Orijinal Mantık: Kullanıcının zaten var olup olmadığını kontrol et ---
        if User.query.filter_by(username=tc_kimlik).first() or Personnel.query.filter_by(tc_kimlik=tc_kimlik).first():
            print(f"\n'{tc_kimlik}' TC Kimlik Numarası veya bu T.C.'ye bağlı bir kullanıcı zaten mevcut.")
            return

        try:
            # --- Orijinal Mantık: Hem personel hem kullanıcı kaydı oluştur ---
            admin_personnel = Personnel(
                ad=ad_str,
                soyad=soyad_str,
                tc_kimlik=tc_kimlik,
                mail=mail,
                onay_durumu='Onaylandı' # Admin direkt onaylı başlar
            )

            admin_user = User(
                username=tc_kimlik,
                role='admin',
                personnel=admin_personnel # Doğrudan ilişki kurma
            )
            admin_user.set_password(password)

            db.session.add(admin_personnel)
            db.session.add(admin_user)
            db.session.commit()

            print("\n----------------------------------------------------")
            print("BAŞARILI! İlk admin kullanıcısı oluşturuldu.")
            print("----------------------------------------------------")

        except Exception as e:
            db.session.rollback()
            print(f"\nKullanıcı oluşturulurken bir HATA oluştu: {e}")
            print("Girdiğiniz T.C. Kimlik Numarası veya E-posta zaten kayıtlı olabilir.")

if __name__ == '__main__':
    create_admin_user()
