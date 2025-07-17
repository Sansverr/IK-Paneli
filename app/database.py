import sqlite3
import click
from flask import current_app, g

GEREKLI_EVRAKLAR = [
    "Nüfus Cüzdanı Fotokopisi", "İkametgah (E-DEVLET)", "Nüfus Kayıt Örneği (E-DEVLET)",
    "Diploma veya Öğrenim Belgesi", "Adli Sicil Kaydı (E-DEVLET)", "Askerlik Durum Belgesi (E-DEVLET)",
    "Vesikalık Fotoğraf", "Banka Hesap Bilgisi", "Ehliyet, SRC, Operatörlük Belgesi",
    "Mesleki Yeterlilik Belgesi", "Sigortalı Hizmet Listesi (E-DEVLET)", "Kan Grubu Kartı veya Beyanı"
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
    # Schema.sql dosyasını kullanmak yerine doğrudan execute ediyoruz
    # Bu kısım eski database.py'daki CREATE TABLE komutlarını içerecek
    cursor = db.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS subeler (id INTEGER PRIMARY KEY AUTOINCREMENT, sube_adi TEXT UNIQUE NOT NULL)')
    cursor.execute('CREATE TABLE IF NOT EXISTS gorevler (id INTEGER PRIMARY KEY AUTOINCREMENT, gorev_adi TEXT UNIQUE NOT NULL)')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS calisanlar (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ad_soyad TEXT NOT NULL, sicil_no TEXT UNIQUE,
        ise_baslama_tarihi TEXT, tel TEXT, yakin_tel TEXT, tc_kimlik TEXT UNIQUE NOT NULL, 
        adres TEXT, iban TEXT, egitim TEXT, ucreti TEXT, aciklama TEXT, isten_cikis_tarihi TEXT,
        yillik_izin_bakiye INTEGER NOT NULL DEFAULT 20, yaka_tipi TEXT,
        yonetici_id INTEGER REFERENCES calisanlar(id), sube_id INTEGER REFERENCES subeler(id),
        gorev_id INTEGER REFERENCES gorevler(id), mail TEXT UNIQUE,
        onay_durumu TEXT NOT NULL DEFAULT 'Onaylandı', admin_notu TEXT
    )''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS kullanicilar (id INTEGER PRIMARY KEY AUTOINCREMENT, password TEXT NOT NULL, 
    role TEXT NOT NULL DEFAULT "user", calisan_id INTEGER UNIQUE NOT NULL REFERENCES calisanlar(id) ON DELETE CASCADE)
    ''')
    # ... Diğer tüm CREATE TABLE komutları buraya ...
    db.commit()


@click.command('init-db')
def init_db_command(app):
    """Mevcut verileri temizler ve yeni tablolar oluşturur."""
    with app.app_context():
        init_db()
        click.echo('Initialized the database.')