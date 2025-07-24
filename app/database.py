# app/database.py
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from datetime import date

# --- SABİT LİSTELER (Orijinal Mantıktan Alındı) ---
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

db = SQLAlchemy()

# --- Yeni Modeller (Orijinal Tablolara Karşılık Gelir) ---
class Departman(db.Model): __tablename__ = 'departmanlar'; id = db.Column(db.Integer, primary_key=True); departman_adi = db.Column(db.String(100), unique=True, nullable=False)
class Sube(db.Model): __tablename__ = 'subeler'; id = db.Column(db.Integer, primary_key=True); sube_adi = db.Column(db.String(100), unique=True, nullable=False)
class Gorev(db.Model): __tablename__ = 'gorevler'; id = db.Column(db.Integer, primary_key=True); gorev_adi = db.Column(db.String(100), unique=True, nullable=False)
class EvrakTipi(db.Model): __tablename__ = 'evrak_tipleri'; id = db.Column(db.Integer, primary_key=True); evrak_adi = db.Column(db.String(255), unique=True, nullable=False); kategori = db.Column(db.String(100), nullable=False)

class User(UserMixin, db.Model):
    __tablename__ = 'kullanicilar'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(50), nullable=False, default='user')
    personnel_id = db.Column(db.Integer, db.ForeignKey('calisanlar.id'), unique=True, nullable=False)
    personnel = db.relationship('Personnel', back_populates='user')
    def set_password(self, password): self.password = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password, password)

class Personnel(db.Model):
    __tablename__ = 'calisanlar'
    id = db.Column(db.Integer, primary_key=True)
    ad = db.Column(db.String(100), nullable=False); soyad = db.Column(db.String(100), nullable=False)
    sicil_no = db.Column(db.String(50), unique=True); tc_kimlik = db.Column(db.String(11), unique=True, nullable=False)
    ise_baslama_tarihi = db.Column(db.Date); isten_cikis_tarihi = db.Column(db.Date); dogum_tarihi = db.Column(db.Date)
    cinsiyet = db.Column(db.String(10)); kan_grubu = db.Column(db.String(10)); tel = db.Column(db.String(20))
    yakin_tel = db.Column(db.String(20)); adres = db.Column(db.String(255)); iban = db.Column(db.String(34))
    egitim = db.Column(db.String(100)); ucreti = db.Column(db.String(50)); aciklama = db.Column(db.Text)
    yillik_izin_bakiye = db.Column(db.Integer, nullable=False, default=20); yaka_tipi = db.Column(db.String(20))
    yonetici_id = db.Column(db.Integer, db.ForeignKey('calisanlar.id')); sube_id = db.Column(db.Integer, db.ForeignKey('subeler.id'))
    departman_id = db.Column(db.Integer, db.ForeignKey('departmanlar.id')); gorev_id = db.Column(db.Integer, db.ForeignKey('gorevler.id'))
    mail = db.Column(db.String(120), unique=True); onay_durumu = db.Column(db.String(20), nullable=False, default='Onay Bekliyor')
    admin_notu = db.Column(db.Text)

    user = db.relationship('User', back_populates='personnel', uselist=False, cascade="all, delete-orphan")
    izin_talepleri = db.relationship('LeaveRequest', backref='personnel', lazy=True, cascade="all, delete-orphan")
    evraklar = db.relationship('Evrak', backref='personnel', lazy=True, cascade="all, delete-orphan")
    hedefler = db.relationship('PersonnelGoal', backref='personnel', lazy=True, cascade="all, delete-orphan")

class LeaveRequest(db.Model): __tablename__ = 'izin_talepleri'; id = db.Column(db.Integer, primary_key=True); calisan_id = db.Column(db.Integer, db.ForeignKey('calisanlar.id'), nullable=False); izin_tipi = db.Column(db.String(50), nullable=False); baslangic_tarihi = db.Column(db.Date, nullable=False); bitis_tarihi = db.Column(db.Date, nullable=False); gun_sayisi = db.Column(db.Integer); aciklama = db.Column(db.Text); durum = db.Column(db.String(20), nullable=False, default='Beklemede'); talep_tarihi = db.Column(db.Date, default=date.today)
class Evrak(db.Model): __tablename__ = 'evraklar'; id = db.Column(db.Integer, primary_key=True); calisan_id = db.Column(db.Integer, db.ForeignKey('calisanlar.id'), nullable=False); evrak_tipi = db.Column(db.String(255), nullable=False); kategori = db.Column(db.String(100), nullable=False); dosya_yolu = db.Column(db.String(255)); yuklendi_mi = db.Column(db.Boolean, nullable=False, default=False); notlar = db.Column(db.Text)
class PerformancePeriod(db.Model): __tablename__ = 'degerlendirme_donemleri'; id = db.Column(db.Integer, primary_key=True); donem_adi = db.Column(db.String(150), nullable=False); baslangic_tarihi = db.Column(db.Date); bitis_tarihi = db.Column(db.Date); durum = db.Column(db.String(20), default='Aktif'); hedefler = db.relationship('PersonnelGoal', backref='donem', lazy='dynamic', cascade="all, delete-orphan")
class PersonnelGoal(db.Model): __tablename__ = 'personel_hedefleri'; id = db.Column(db.Integer, primary_key=True); calisan_id = db.Column(db.Integer, db.ForeignKey('calisanlar.id'), nullable=False); donem_id = db.Column(db.Integer, db.ForeignKey('degerlendirme_donemleri.id'), nullable=False); hedef_aciklamasi = db.Column(db.Text); agirlik = db.Column(db.Integer, default=100)
class PasswordResetRequest(db.Model): __tablename__ = 'sifre_sifirlama_talepleri'; id = db.Column(db.Integer, primary_key=True); calisan_id = db.Column(db.Integer, db.ForeignKey('calisanlar.id'), nullable=False); talep_tarihi = db.Column(db.Date, default=date.today); durum = db.Column(db.String(20), default='Beklemede'); personnel = db.relationship('Personnel')
