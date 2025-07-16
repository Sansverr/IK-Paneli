import sqlite3
from werkzeug.security import generate_password_hash

GEREKLI_EVRAKLAR = [
    "Nüfus Cüzdanı Fotokopisi", "İkametgah (E-DEVLET)", "Nüfus Kayıt Örneği (E-DEVLET)",
    "Diploma veya Öğrenim Belgesi", "Adli Sicil Kaydı (E-DEVLET)", "Askerlik Durum Belgesi (E-DEVLET)",
    "Vesikalık Fotoğraf", "Banka Hesap Bilgisi", "Ehliyet, SRC, Operatörlük Belgesi",
    "Mesleki Yeterlilik Belgesi", "Sigortalı Hizmet Listesi (E-DEVLET)", "Kan Grubu Kartı veya Beyanı"
]

def init_db():
    conn = sqlite3.connect('hr.db')
    cursor = conn.cursor()

    # Mevcut tablolardaki sütunları eklemeyi dene (hata vermeden geçer)
    try:
        cursor.execute('ALTER TABLE calisanlar ADD COLUMN yillik_izin_bakiye INTEGER NOT NULL DEFAULT 20')
        cursor.execute('ALTER TABLE calisanlar ADD COLUMN yonetici_id INTEGER REFERENCES calisanlar(id)')
        cursor.execute('ALTER TABLE kullanicilar ADD COLUMN calisan_id INTEGER UNIQUE REFERENCES calisanlar(id)')
    except sqlite3.OperationalError:
        pass 

    # Mevcut Tablolar
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS calisanlar (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ad_soyad TEXT NOT NULL, sicil_no TEXT UNIQUE,
        ise_baslama_tarihi TEXT, sube TEXT, gorevi TEXT, yaka_tipi TEXT,
        tel TEXT, yakin_tel TEXT, tc_kimlik TEXT, adres TEXT, iban TEXT, 
        egitim TEXT, ucreti TEXT, aciklama TEXT, isten_cikis_tarihi TEXT,
        yillik_izin_bakiye INTEGER NOT NULL DEFAULT 20,
        yonetici_id INTEGER REFERENCES calisanlar(id)
    )
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS kullanicilar (
        id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'user', calisan_id INTEGER UNIQUE REFERENCES calisanlar(id)
    )
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS evraklar (
        id INTEGER PRIMARY KEY AUTOINCREMENT, calisan_id INTEGER, evrak_tipi TEXT NOT NULL, 
        dosya_yolu TEXT, yuklendi_mi BOOLEAN NOT NULL DEFAULT 0,
        FOREIGN KEY (calisan_id) REFERENCES calisanlar (id) ON DELETE CASCADE
    )
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS izin_talepleri (
        id INTEGER PRIMARY KEY AUTOINCREMENT, calisan_id INTEGER NOT NULL, izin_tipi TEXT NOT NULL,
        baslangic_tarihi TEXT NOT NULL, bitis_tarihi TEXT NOT NULL, gun_sayisi INTEGER NOT NULL,
        aciklama TEXT, talep_tarihi TEXT NOT NULL, durum TEXT NOT NULL DEFAULT 'Beklemede',
        yonetici_notu TEXT, FOREIGN KEY (calisan_id) REFERENCES calisanlar (id) ON DELETE CASCADE
    )
    ''')

    # --- YENİ: Performans Modülü Tabloları ---
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS degerlendirme_donemleri (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        donem_adi TEXT NOT NULL,
        baslangic_tarihi TEXT NOT NULL,
        bitis_tarihi TEXT NOT NULL,
        durum TEXT NOT NULL DEFAULT 'Aktif' -- Aktif, Tamamlandı
    )
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS personel_hedefleri (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        calisan_id INTEGER NOT NULL,
        donem_id INTEGER NOT NULL,
        hedef_aciklamasi TEXT NOT NULL,
        olcum_kriteri TEXT,
        agirlik INTEGER DEFAULT 100, -- Hedefin yüzdesel ağırlığı
        calisan_degerlendirmesi TEXT,
        yonetici_degerlendirmesi TEXT,
        sonuc INTEGER, -- 1-5 arası puanlama gibi
        FOREIGN KEY (calisan_id) REFERENCES calisanlar(id) ON DELETE CASCADE,
        FOREIGN KEY (donem_id) REFERENCES degerlendirme_donemleri(id) ON DELETE CASCADE
    )
    ''')

    # --- İlk kullanıcıları oluşturma (varsa dokunmaz) ---
    cursor.execute("SELECT id FROM kullanicilar WHERE username = ?", ('yonetici',))
    if cursor.fetchone() is None:
        yonetici_sifre = generate_password_hash("YoneticiSifre456")
        cursor.execute("INSERT INTO kullanicilar (username, password, role) VALUES (?, ?, ?)",
                       ('yonetici', yonetici_sifre, 'admin'))
    cursor.execute("SELECT id FROM kullanicilar WHERE username = ?", ('ik_uzmani',))
    if cursor.fetchone() is None:
        ik_sifre = generate_password_hash("GuvenliSifre123")
        cursor.execute("INSERT INTO kullanicilar (username, password, role) VALUES (?, ?, ?)",
                       ('ik_uzmani', ik_sifre, 'user'))
    conn.commit()
    conn.close()