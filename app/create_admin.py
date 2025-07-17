import sqlite3
from werkzeug.security import generate_password_hash
import getpass
import os
from app.database import init_db 

DB_NAME = 'hr.db'

def force_create_db_and_admin():
    if os.path.exists(DB_NAME):
        print(f"Eski '{DB_NAME}' dosyası bulundu ve siliniyor...")
        os.remove(DB_NAME)
        print("Eski veritabanı başarıyla silindi.")

    print("\nVeritabanı ve tablolar oluşturuluyor...")
    init_db()
    print("Veritabanı şeması başarıyla oluşturuldu.")

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    print("\n--- İlk Admin Kullanıcı Oluşturma ---")
    ad_soyad = input("Adınız ve Soyadınız: ")
    tc_kimlik = input("TC Kimlik Numaranız (Giriş için): ")
    mail = input("E-posta Adresiniz (Şifre sıfırlama için): ")
    password = getpass.getpass("Oluşturmak istediğiniz şifre: ")

    try:
        cursor.execute("INSERT INTO calisanlar (ad_soyad, tc_kimlik, mail, onay_durumu) VALUES (?, ?, ?, ?)",
                       (ad_soyad, tc_kimlik, mail, 'Onaylandı'))
        calisan_id = cursor.lastrowid

        hashed_password = generate_password_hash(password)
        cursor.execute("INSERT INTO kullanicilar (password, role, calisan_id) VALUES (?, ?, ?)",
                       (hashed_password, 'admin', calisan_id))

        conn.commit()
        print("\n----------------------------------------------------")
        print("BAŞARILI! İlk admin kullanıcısı oluşturuldu.")
        print("Artık 'Run' düğmesine basarak paneli başlatabilirsiniz.")
        print("----------------------------------------------------")
    except sqlite3.IntegrityError as e:
         print(f"\nKullanıcı oluşturulurken bir HATA oluştu: {e}")
         print("Girdiğiniz T.C. Kimlik Numarası veya E-posta zaten kayıtlı olabilir.")
    except Exception as e:
        print(f"\nKullanıcı oluşturulurken bir hata oluştu: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    force_create_db_and_admin()