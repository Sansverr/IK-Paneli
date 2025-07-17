import sqlite3
from werkzeug.security import generate_password_hash
import getpass
import os

# BU SCRIPT, TÜM İŞLEMLERİ KENDİ İÇİNDE YAPAR. (database.py'a GÜVENMEZ)

DB_NAME = 'hr.db'

def force_create_db_and_admin():
    # --- Adım 1: ESKİ VERİTABANINI SİL ---
    if os.path.exists(DB_NAME):
        print(f"Eski '{DB_NAME}' dosyası bulundu ve siliniyor...")
        os.remove(DB_NAME)
        print("Eski veritabanı başarıyla silindi.")

    # --- Adım 2: VERİTABANINI VE TABLOLARI SIFIRDAN OLUŞTUR ---
    print("\nVeritabanı ve tablolar sıfırdan oluşturuluyor...")
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        # TÜM TABLO OLUŞTURMA KOMUTLARI ARTIK BURADA
        cursor.execute('CREATE TABLE IF NOT EXISTS subeler (id INTEGER PRIMARY KEY AUTOINCREMENT, sube_adi TEXT UNIQUE NOT NULL)')
        cursor.execute('CREATE TABLE IF NOT EXISTS gorevler (id INTEGER PRIMARY KEY AUTOINCREMENT, gorev_adi TEXT UNIQUE NOT NULL)')

        # 'mail' SÜTUNUNU İÇEREN DOĞRU calisanlar TABLOSU
        cursor.execute('''
        CREATE TABLE calisanlar (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ad_soyad TEXT NOT NULL, sicil_no TEXT UNIQUE,
            ise_baslama_tarihi TEXT, tel TEXT, yakin_tel TEXT, tc_kimlik TEXT UNIQUE NOT NULL, 
            adres TEXT, iban TEXT, egitim TEXT, ucreti TEXT, aciklama TEXT, isten_cikis_tarihi TEXT,
            yillik_izin_bakiye INTEGER NOT NULL DEFAULT 20, yaka_tipi TEXT,
            yonetici_id INTEGER REFERENCES calisanlar(id),
            sube_id INTEGER REFERENCES subeler(id),
            gorev_id INTEGER REFERENCES gorevler(id),
            mail TEXT UNIQUE
        )
        ''')

        cursor.execute('CREATE TABLE IF NOT EXISTS kullanicilar (id INTEGER PRIMARY KEY AUTOINCREMENT, password TEXT NOT NULL, role TEXT NOT NULL DEFAULT "user", calisan_id INTEGER UNIQUE REFERENCES calisanlar(id) NOT NULL)')
        cursor.execute('CREATE TABLE IF NOT EXISTS sifre_sifirlama_talepleri (id INTEGER PRIMARY KEY AUTOINCREMENT, calisan_id INTEGER NOT NULL, talep_tarihi TEXT NOT NULL, durum TEXT NOT NULL DEFAULT "Beklemede", FOREIGN KEY (calisan_id) REFERENCES calisanlar(id) ON DELETE CASCADE)')
        cursor.execute('CREATE TABLE IF NOT EXISTS evraklar (id INTEGER PRIMARY KEY AUTOINCREMENT, calisan_id INTEGER, evrak_tipi TEXT NOT NULL, dosya_yolu TEXT, yuklendi_mi BOOLEAN NOT NULL DEFAULT 0, FOREIGN KEY (calisan_id) REFERENCES calisanlar (id) ON DELETE CASCADE)')
        cursor.execute('CREATE TABLE IF NOT EXISTS izin_talepleri (id INTEGER PRIMARY KEY AUTOINCREMENT, calisan_id INTEGER NOT NULL, izin_tipi TEXT NOT NULL, baslangic_tarihi TEXT NOT NULL, bitis_tarihi TEXT NOT NULL, gun_sayisi INTEGER NOT NULL, aciklama TEXT, talep_tarihi TEXT NOT NULL, durum TEXT NOT NULL DEFAULT "Beklemede", yonetici_notu TEXT, FOREIGN KEY (calisan_id) REFERENCES calisanlar (id) ON DELETE CASCADE)')
        cursor.execute('CREATE TABLE IF NOT EXISTS degerlendirme_donemleri (id INTEGER PRIMARY KEY AUTOINCREMENT, donem_adi TEXT NOT NULL, baslangic_tarihi TEXT NOT NULL, bitis_tarihi TEXT NOT NULL, durum TEXT NOT NULL DEFAULT "Aktif")')
        cursor.execute('CREATE TABLE IF NOT EXISTS personel_hedefleri (id INTEGER PRIMARY KEY AUTOINCREMENT, calisan_id INTEGER NOT NULL, donem_id INTEGER NOT NULL, hedef_aciklamasi TEXT NOT NULL, olcum_kriteri TEXT, agirlik INTEGER DEFAULT 100, calisan_degerlendirmesi TEXT, yonetici_degerlendirmesi TEXT, sonuc INTEGER, FOREIGN KEY (calisan_id) REFERENCES calisanlar(id) ON DELETE CASCADE, FOREIGN KEY (donem_id) REFERENCES degerlendirme_donemleri(id) ON DELETE CASCADE)')

        conn.commit()
        print("Tüm tablolar başarıyla oluşturuldu.")

    except Exception as e:
        print(f"Veritabanı oluşturulurken bir hata oluştu: {e}")
        if conn:
            conn.close()
        return

    # --- Adım 3: İLK ADMİN KULLANICISINI OLUŞTUR ---
    print("\n--- İlk Admin Kullanıcı Oluşturma ---")
    ad_soyad = input("Adınız ve Soyadınız: ")
    tc_kimlik = input("TC Kimlik Numaranız (Giriş için): ")
    mail = input("E-posta Adresiniz (Şifre sıfırlama için): ")
    password = getpass.getpass("Oluşturmak istediğiniz şifre: ")

    try:
        cursor.execute("INSERT INTO calisanlar (ad_soyad, tc_kimlik, mail) VALUES (?, ?, ?)", (ad_soyad, tc_kimlik, mail))
        calisan_id = cursor.lastrowid

        hashed_password = generate_password_hash(password)
        cursor.execute("INSERT INTO kullanicilar (password, role, calisan_id) VALUES (?, ?, ?)", (hashed_password, 'admin', calisan_id))

        conn.commit()
        print("\n----------------------------------------------------")
        print("BAŞARILI! İlk admin kullanıcısı oluşturuldu.")
        print("Artık 'Run' düğmesine basarak paneli başlatabilirsiniz.")
        print("----------------------------------------------------")
    except Exception as e:
        print(f"\nKullanıcı oluşturulurken bir hata oluştu: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    force_create_db_and_admin()