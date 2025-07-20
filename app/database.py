# app/database.py

import sqlite3
import click
from flask import current_app, g

# --- SABİT LİSTELER ---
# Veritabanı ilk kez oluşturulduğunda eklenecek varsayılan evraklar
GEREKLI_OZLUK_EVRAKLARI = [
    "Nüfus Cüzdanı Fotokopisi", "İkametgah (E-DEVLET)", "Nüfus Kayıt Örneği (E-DEVLET)",
    "Diploma veya Öğrenim Belgesi", "Adli Sicil Kaydı (E-DEVLET)", "Askerlik Durum Belgesi (E-DEVLET)",
    "Vesikalık Fotoğraf", "Banka Hesap Bilgisi", "Ehliyet, SRC, Operatörlük Belgesi",
    "Mesleki Yeterlilik Belgesi", "Sigortalı Hizmet Listesi (E-DEVLET)", "Kan Grubu Kartı veya Beyanı"
]
GEREKLI_ISE_BASLANGIC_SURECLERI = [
    "İŞe giriş bilgi formu", "İmzalı İş Sözleşmesi", "ALKOL TAAHHÜTNAME",
    "Fazla Çalışma Muvafakatnamesi", "Güvenlik ve Koruyucu Malzemeler", "İş Güvenliği Talimat ve Tutanağı",
    "Zimmet Formu", "İŞ SÖZLEŞMESİ ÇALIŞAN GİZLİLİK EK PROTOKOLÜ", "İŞYERİ PERSONEL DİSİPLİN YÖNETMELİĞİ",
    "PERSONEL İŞE BAŞLAMA FORMU", "Şirket KVKK VERİ RIZA BEYAN FORMU", "Personele teslim edilen zimmetler"
]

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(
            current_app.config['DATABASE'],
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        g.db.row_factory = sqlite3.Row
    return g.db

def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    db = get_db()
    cursor = db.cursor()

    # --- DEĞİŞİKLİK BURADA: COLLATE NOCASE eklendi ---
    # Bu komut, metin karşılaştırmalarında büyük/küçük harf ayrımını ortadan kaldırır.
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

    # --- YENİ TABLO ---
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS evrak_tipleri (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        evrak_adi TEXT UNIQUE NOT NULL COLLATE NOCASE,
        kategori TEXT NOT NULL 
    )''')

    # Varsayılan evrakları yeni tabloya ekle (sadece tablo boşsa)
    count = cursor.execute("SELECT COUNT(id) FROM evrak_tipleri").fetchone()[0]
    if count == 0:
        for evrak in GEREKLI_OZLUK_EVRAKLARI:
            cursor.execute("INSERT INTO evrak_tipleri (evrak_adi, kategori) VALUES (?, ?)", (evrak, 'Özlük'))
        for surec in GEREKLI_ISE_BASLANGIC_SURECLERI:
            cursor.execute("INSERT INTO evrak_tipleri (evrak_adi, kategori) VALUES (?, ?)", (surec, 'İşe Başlangıç'))

    db.commit()


@click.command('init-db')
def init_db_command(app):
    with app.app_context():
        init_db()
        click.echo('Initialized the database.')