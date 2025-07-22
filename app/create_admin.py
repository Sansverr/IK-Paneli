# app/create_admin.py

import sqlite3
from werkzeug.security import generate_password_hash
import getpass
import os

# app/database.py dosyasından merkezi listeleri import et
from app.database import GEREKLI_OZLUK_EVRAKLARI, GEREKLI_ISE_BASLANGIC_SURECLERI

DB_NAME = 'hr.db'
def force_create_db_and_admin():
    if os.path.exists(DB_NAME):
        print(f"Eski '{DB_NAME}' dosyası bulundu ve siliniyor...")
        os.remove(DB_NAME)
        print("Eski veritabanı başarıyla silindi.")

    print("\nVeritabanı ve tablolar oluşturuluyor...")

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute('CREATE TABLE IF NOT EXISTS departmanlar (id INTEGER PRIMARY KEY AUTOINCREMENT, departman_adi TEXT UNIQUE NOT NULL COLLATE NOCASE)')
    cursor.execute('CREATE TABLE IF NOT EXISTS subeler (id INTEGER PRIMARY KEY AUTOINCREMENT, sube_adi TEXT UNIQUE NOT NULL COLLATE NOCASE)')
    cursor.execute('CREATE TABLE IF NOT EXISTS gorevler (id INTEGER PRIMARY KEY AUTOINCREMENT, gorev_adi TEXT UNIQUE NOT NULL COLLATE NOCASE)')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS calisanlar (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ad TEXT NOT NULL,
        soyad TEXT NOT NULL,
        sicil_no TEXT,
        tc_kimlik TEXT UNIQUE NOT NULL,
        ise_baslama_tarihi TEXT,
        isten_cikis_tarihi TEXT,
        dogum_tarihi TEXT,
        cinsiyet TEXT,
        kan_grubu TEXT,
        tel TEXT,
        yakin_tel TEXT,
        adres TEXT,
        iban TEXT,
        egitim TEXT,
        ucreti TEXT,
        aciklama TEXT,
        yillik_izin_bakiye INTEGER NOT NULL DEFAULT 20,
        yaka_tipi TEXT,
        yonetici_id INTEGER REFERENCES calisanlar(id),
        sube_id INTEGER REFERENCES subeler(id),
        departman_id INTEGER REFERENCES departmanlar(id),
        gorev_id INTEGER REFERENCES gorevler(id),
        mail TEXT UNIQUE,
        onay_durumu TEXT NOT NULL DEFAULT 'Onaylandı',
        admin_notu TEXT
    )''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS kullanicilar (id INTEGER PRIMARY KEY AUTOINCREMENT, password TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT "user", calisan_id INTEGER UNIQUE NOT NULL REFERENCES calisanlar(id) ON DELETE CASCADE)
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS izin_talepleri (id INTEGER PRIMARY KEY AUTOINCREMENT, calisan_id INTEGER NOT NULL REFERENCES calisanlar(id) ON DELETE CASCADE,
    izin_tipi TEXT NOT NULL, baslangic_tarihi TEXT NOT NULL, bitis_tarihi TEXT NOT NULL, gun_sayisi INTEGER, aciklama TEXT,
    durum TEXT NOT NULL DEFAULT 'Beklemede', talep_tarihi TEXT)
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS sifre_sifirlama_talepleri (id INTEGER PRIMARY KEY AUTOINCREMENT, calisan_id INTEGER NOT NULL REFERENCES calisanlar(id) ON DELETE CASCADE,
    talep_tarihi TEXT, durum TEXT DEFAULT 'Beklemede')
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS degerlendirme_donemleri (id INTEGER PRIMARY KEY AUTOINCREMENT, donem_adi TEXT NOT NULL, baslangic_tarihi TEXT, bitis_tarihi TEXT,
    durum TEXT DEFAULT 'Aktif')
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS personel_hedefleri (id INTEGER PRIMARY KEY AUTOINCREMENT, calisan_id INTEGER NOT NULL REFERENCES calisanlar(id) ON DELETE CASCADE,
    donem_id INTEGER NOT NULL REFERENCES degerlendirme_donemleri(id) ON DELETE CASCADE, hedef_aciklamasi TEXT, agirlik INTEGER DEFAULT 100)
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS evraklar (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        calisan_id INTEGER NOT NULL REFERENCES calisanlar(id) ON DELETE CASCADE,
        evrak_tipi TEXT NOT NULL,
        kategori TEXT NOT NULL,
        dosya_yolu TEXT,
        yuklendi_mi INTEGER NOT NULL DEFAULT 0,
        notlar TEXT
    )''')

    # --- YENİ TABLO VE VERİ EKLEME ---
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS evrak_tipleri (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        evrak_adi TEXT UNIQUE NOT NULL COLLATE NOCASE,
        kategori TEXT NOT NULL
    )''')

    for evrak in GEREKLI_OZLUK_EVRAKLARI:
        cursor.execute("INSERT OR IGNORE INTO evrak_tipleri (evrak_adi, kategori) VALUES (?, ?)", (evrak, 'Özlük'))
    for surec in GEREKLI_ISE_BASLANGIC_SURECLERI:
        cursor.execute("INSERT OR IGNORE INTO evrak_tipleri (evrak_adi, kategori) VALUES (?, ?)", (surec, 'İşe Başlangıç'))

    conn.commit()
    print("Veritabanı şeması başarıyla oluşturuldu.")

    print("\n--- İlk Admin Kullanıcı Oluşturma ---")
    ad_soyad_input = input("Adınız ve Soyadınız: ")
    tc_kimlik = input("TC Kimlik Numaranız (Giriş için): ")
    mail = input("E-posta Adresiniz (Şifre sıfırlama için): ")
    password = getpass.getpass("Oluşturmak istediğiniz şifre: ")

    parts = ad_soyad_input.strip().split()
    soyad = parts[-1].title() if parts else ""
    ad = " ".join(parts[:-1]).title() if len(parts) > 1 else (parts[0].title() if parts else "")
    if not ad and soyad: ad = soyad; soyad = ""

    try:
        cursor.execute("INSERT INTO calisanlar (ad, soyad, tc_kimlik, mail, onay_durumu) VALUES (?, ?, ?, ?, ?)",
                       (ad, soyad, tc_kimlik, mail, 'Onaylandı'))
        calisan_id = cursor.lastrowid

        hashed_password = generate_password_hash(password)
        cursor.execute("INSERT INTO kullanicilar (password, role, calisan_id) VALUES (?, ?, ?)",
                       (hashed_password, 'admin', calisan_id))

        conn.commit()
        print("\n----------------------------------------------------")
        print("BAŞARILI! İlk admin kullanıcısı oluşturuldu.")
        print("Artık `python run.py` komutu ile paneli başlatabilirsiniz.")
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