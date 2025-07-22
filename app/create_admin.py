import os
import sys
from getpass import getpass

# Bu betiğin, 'app' klasörünü bulabilmesi için projenin ana dizinini Python yoluna ekle.
# Bu, komutun ana dizinden çalıştırıldığında import hatalarını önler.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, db
from app.database import User, Personnel  # Personnel modelini de import et

def create_admin_user():
    """Yeni bir yönetici kullanıcı ve buna bağlı bir personel kaydı oluşturur."""
    app = create_app()
    with app.app_context():
        # Kullanıcı adı olarak TC Kimlik Numarası iste
        tc_kimlik_no = input("Yönetici için TC Kimlik Numarası girin: ")
        if User.query.filter_by(username=tc_kimlik_no).first():
            print(f"'{tc_kimlik_no}' TC Kimlik Numaralı kullanıcı zaten mevcut.")
            return

        password = getpass("Şifreyi girin: ")
        confirm_password = getpass("Şifreyi tekrar girin: ")

        if password != confirm_password:
            print("Şifreler eşleşmiyor.")
            return

        # Yeni yönetici kullanıcısını oluştur
        admin_user = User(username=tc_kimlik_no, role='admin')
        admin_user.set_password(password)

        # Yönetici için basit bir personel kaydı oluştur
        # Bu, panelin tüm fonksiyonlarının düzgün çalışmasını sağlar
        admin_personnel = Personnel(
            name="Yönetici",
            surname="Hesabı",
            tc_kimlik_no=tc_kimlik_no,
            email=f"admin@{tc_kimlik_no}.local" # Benzersiz bir e-posta
        )

        # Kullanıcıyı personel kaydına bağla
        admin_user.personnel.append(admin_personnel)

        db.session.add(admin_user)
        db.session.add(admin_personnel)
        db.session.commit()
        print(f"'{tc_kimlik_no}' TC Kimlik Numaralı yönetici kullanıcısı başarıyla oluşturuldu.")

if __name__ == '__main__':
    create_admin_user()
