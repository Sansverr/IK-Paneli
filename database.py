import sqlite3
from werkzeug.security import generate_password_hash

# Gerekli evraklar listesi
GEREKLI_EVRAKLAR = [
    "Nüfus Cüzdanı Fotokopisi", "İkametgah (E-DEVLET)", "Nüfus Kayıt Örneği (E-DEVLET)",
    "Diploma veya Öğrenim Belgesi", "Adli Sicil Kaydı (E-DEVLET)", "Askerlik Durum Belgesi (E-DEVLET)",
    "Vesikalık Fotoğraf", "Banka Hesap Bilgisi", "Ehliyet, SRC, Operatörlük Belgesi",
    "Mesleki Yeterlilik Belgesi", "Sigortalı Hizmet Listesi (E-DEVLET)", "Kan Grubu Kartı veya Beyanı"
]

def init_db():
    """Veritabanını ve tabloları en güncel şemaya göre oluşturur veya günceller."""
    conn = sqlite3.connect('hr.db')
    cursor = conn.cursor()

    # --- Mevcut Sütunları Eklemeyi Dene (Hata vermeden geçer) ---
    try:
        cursor.execute('ALTER TABLE calisanlar ADD COLUMN onay_durumu TEXT NOT NULL DEFAULT "Onaylandı"')
        cursor.execute('ALTER TABLE calisanlar ADD COLUMN admin_notu TEXT')
    except sqlite3.OperationalError:
        pass

    # --- İlişkisel ve Ana Tablolar ---
    cursor.execute('CREATE TABLE IF NOT EXISTS subeler (id INTEGER PRIMARY KEY AUTOINCREMENT, sube_adi TEXT UNIQUE NOT NULL)')
    cursor.execute('CREATE TABLE IF NOT EXISTS gorevler (id INTEGER PRIMARY KEY AUTOINCREMENT, gorev_adi TEXT UNIQUE NOT NULL)')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS calisanlar (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        ad_soyad TEXT NOT NULL, 
        sicil_no TEXT UNIQUE,
        ise_baslama_tarihi TEXT, 
        tel TEXT, 
        yakin_tel TEXT, 
        tc_kimlik TEXT UNIQUE NOT NULL, 
        adres TEXT, 
        iban TEXT, 
        egitim TEXT, 
        ucreti TEXT, 
        aciklama TEXT, 
        isten_cikis_tarihi TEXT,
        yillik_izin_bakiye INTEGER NOT NULL DEFAULT 20, 
        yaka_tipi TEXT,
        yonetici_id INTEGER REFERENCES calisanlar(id),
        sube_id INTEGER REFERENCES subeler(id),
        gorev_id INTEGER REFERENCES gorevler(id),
        mail TEXT UNIQUE,
        onay_durumu TEXT NOT NULL DEFAULT 'Onaylandı', -- Onay Bekliyor, Onaylandı, Reddedildi
        admin_notu TEXT
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS kullanicilar (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        password TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'user', 
        calisan_id INTEGER UNIQUE NOT NULL REFERENCES calisanlar(id) ON DELETE CASCADE
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS sifre_sifirlama_talepleri (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        calisan_id INTEGER NOT NULL,
        talep_tarihi TEXT NOT NULL,
        durum TEXT NOT NULL DEFAULT 'Beklemede',
        FOREIGN KEY (calisan_id) REFERENCES calisanlar(id) ON DELETE CASCADE
    )
    ''')

    cursor.execute('CREATE TABLE IF NOT EXISTS evraklar (id INTEGER PRIMARY KEY AUTOINCREMENT, calisan_id INTEGER, evrak_tipi TEXT NOT NULL, dosya_yolu TEXT, yuklendi_mi BOOLEAN NOT NULL DEFAULT 0, FOREIGN KEY (calisan_id) REFERENCES calisanlar (id) ON DELETE CASCADE)')
    cursor.execute('CREATE TABLE IF NOT EXISTS izin_talepleri (id INTEGER PRIMARY KEY AUTOINCREMENT, calisan_id INTEGER NOT NULL, izin_tipi TEXT NOT NULL, baslangic_tarihi TEXT NOT NULL, bitis_tarihi TEXT NOT NULL, gun_sayisi INTEGER NOT NULL, aciklama TEXT, talep_tarihi TEXT NOT NULL, durum TEXT NOT NULL DEFAULT "Beklemede", yonetici_notu TEXT, FOREIGN KEY (calisan_id) REFERENCES calisanlar (id) ON DELETE CASCADE)')
    cursor.execute('CREATE TABLE IF NOT EXISTS degerlendirme_donemleri (id INTEGER PRIMARY KEY AUTOINCREMENT, donem_adi TEXT NOT NULL, baslangic_tarihi TEXT NOT NULL, bitis_tarihi TEXT NOT NULL, durum TEXT NOT NULL DEFAULT "Aktif")')
    cursor.execute('CREATE TABLE IF NOT EXISTS personel_hedefleri (id INTEGER PRIMARY KEY AUTOINCREMENT, calisan_id INTEGER NOT NULL, donem_id INTEGER NOT NULL, hedef_aciklamasi TEXT NOT NULL, olcum_kriteri TEXT, agirlik INTEGER DEFAULT 100, calisan_degerlendirmesi TEXT, yonetici_degerlendirmesi TEXT, sonuc INTEGER, FOREIGN KEY (calisan_id) REFERENCES calisanlar(id) ON DELETE CASCADE, FOREIGN KEY (donem_id) REFERENCES degerlendirme_donemleri(id) ON DELETE CASCADE)')

    conn.commit()
    conn.close()