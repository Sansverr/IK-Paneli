import sqlite3

GEREKLI_EVRAKLAR = [
    "Nüfus Cüzdanı Fotokopisi", "İkametgah (E-DEVLET)", "Nüfus Kayıt Örneği (E-DEVLET)",
    "Diploma veya Öğrenim Belgesi", "Adli Sicil Kaydı (E-DEVLET)", "Askerlik Durum Belgesi (E-DEVLET)",
    "Vesikalık Fotoğraf", "Banka Hesap Bilgisi", "Ehliyet, SRC, Operatörlük Belgesi",
    "Mesleki Yeterlilik Belgesi", "Sigortalı Hizmet Listesi (E-DEVLET)", "Kan Grubu Kartı veya Beyanı"
]

def init_db():
    conn = sqlite3.connect('hr.db')
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS calisanlar (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ise_baslama_tarihi TEXT, ad_soyad TEXT NOT NULL, sube TEXT,
        sicil_no TEXT UNIQUE, egitim TEXT, tel TEXT, gorevi TEXT,
        ucreti TEXT, tc_kimlik TEXT, adres TEXT, iban TEXT,
        aciklama TEXT, yakin_tel TEXT, yaka_tipi TEXT,
        isten_cikis_tarihi TEXT
    )
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS evraklar (
        id INTEGER PRIMARY KEY AUTOINCREMENT, calisan_id INTEGER,
        evrak_tipi TEXT NOT NULL, dosya_yolu TEXT,
        yuklendi_mi BOOLEAN NOT NULL DEFAULT 0,
        FOREIGN KEY (calisan_id) REFERENCES calisanlar (id) ON DELETE CASCADE
    )
    ''')
    conn.commit()
    conn.close()