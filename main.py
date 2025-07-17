from flask import Flask, render_template, request, redirect, url_for, g, flash, send_from_directory, session, make_response
import sqlite3
import os
import random
import string
import smtplib
from email.mime.text import MIMEText
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from database import init_db, GEREKLI_EVRAKLAR
from datetime import datetime, timedelta
from functools import wraps
import io
import openpyxl
from fpdf import FPDF

# --- E-posta Ayarları (Bu bilgileri Replit Secrets bölümüne eklemelisiniz) ---
SMTP_SERVER = os.environ.get('SMTP_SERVER')
SMTP_PORT = int(os.environ.get('SMTP_PORT', 587))
SMTP_USERNAME = os.environ.get('SMTP_USERNAME')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD')
SENDER_EMAIL = os.environ.get('SENDER_EMAIL')

# --- Uygulama Ayarları ---
DATABASE = 'hr.db'
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'acil-durum-icin-cok-daha-guvenli-bir-anahtar-yazin')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- Veritabanı ve Başlangıç Verileri ---
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

with app.app_context():
    init_db()
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("INSERT OR IGNORE INTO subeler (sube_adi) VALUES (?), (?), (?)", ('Genel Merkez', 'Üretim', 'AR-GE'))
        cursor.execute("INSERT OR IGNORE INTO gorevler (gorev_adi) VALUES (?), (?), (?), (?)", ('Yönetici', 'Mühendis', 'Teknisyen', 'Operatör'))
        db.commit()
    except sqlite3.IntegrityError:
        pass 
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# --- Yardımcı Fonksiyonlar ---
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def generate_random_password(length=10):
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for i in range(length))

def send_password_email(recipient_email, new_password):
    if not all([SMTP_SERVER, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, SENDER_EMAIL]):
        print("UYARI: E-posta ayarları (SMTP) Replit Secrets'ta tam olarak tanımlanmamış. E-posta gönderilemedi.")
        return False
    try:
        msg = MIMEText(f"Sayın personelimiz,\n\nİK Paneli için yeni şifreniz aşağıda belirtilmiştir. Güvenliğiniz için giriş yaptıktan sonra şifrenizi değiştirmenizi öneririz.\n\nYeni Şifreniz: {new_password}\n\nİyi çalışmalar dileriz.", "plain", "utf-8")
        msg['Subject'] = 'İK Paneli Yeni Şifre Bilgilendirmesi'
        msg['From'] = SENDER_EMAIL
        msg['To'] = recipient_email

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"E-posta gönderim hatası: {e}")
        return False

# --- DECORATOR'LAR ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Bu sayfayı görüntülemek için lütfen giriş yapın.", "warning")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('role') != 'admin':
            flash("Bu sayfaya erişim yetkiniz bulunmamaktadır.", "danger")
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def personnel_linked_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "calisan_id" not in session or session["calisan_id"] is None:
            return render_template('unlinked_user.html')
        return f(*args, **kwargs)
    return decorated_function

# --- Ortak Veri Yükleyici ---
@app.before_request
def load_common_data():
    g.pending_approvals = 0
    if session.get('role') == 'admin':
        db = get_db()
        g.pending_approvals = db.execute("SELECT COUNT(id) FROM calisanlar WHERE onay_durumu = 'Onay Bekliyor'").fetchone()[0]


# --- GİRİŞ, ÇIKIŞ VE ŞİFRE İŞLEMLERİ ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        tc_kimlik = request.form.get('tc_kimlik')
        password = request.form.get('password')
        db = get_db()
        personnel = db.execute('SELECT * FROM calisanlar WHERE tc_kimlik = ? AND onay_durumu = "Onaylandı"', (tc_kimlik,)).fetchone()

        if personnel:
            user = db.execute('SELECT * FROM kullanicilar WHERE calisan_id = ?', (personnel['id'],)).fetchone()
            if user and check_password_hash(user['password'], password):
                session['user_id'] = user['id']
                session['role'] = user['role']
                session['calisan_id'] = user['calisan_id']
                session['ad_soyad'] = personnel['ad_soyad']
                return redirect(url_for('dashboard'))

        flash("Geçersiz TC Kimlik Numarası, şifre veya hesabınız henüz onaylanmamış olabilir!", "danger")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("Başarıyla çıkış yaptınız.", "info")
    return redirect(url_for('login'))

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        tc_kimlik = request.form.get('tc_kimlik')
        db = get_db()
        personnel = db.execute('SELECT id FROM calisanlar WHERE tc_kimlik = ?', (tc_kimlik,)).fetchone()

        if personnel:
            existing_request = db.execute("SELECT id FROM sifre_sifirlama_talepleri WHERE calisan_id = ? AND durum = 'Beklemede'", (personnel['id'],)).fetchone()
            if existing_request:
                flash("Bu personel için zaten beklemede olan bir şifre sıfırlama talebi mevcut.", "warning")
            else:
                db.execute("INSERT INTO sifre_sifirlama_talepleri (calisan_id, talep_tarihi) VALUES (?, ?)", (personnel['id'], datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                db.commit()
                flash("Şifre sıfırlama talebiniz sistem yöneticisine iletilmiştir.", "success")
        else:
            flash("Bu TC Kimlik Numarasına sahip bir personel bulunamadı.", "danger")

        return redirect(url_for('login'))
    return render_template('forgot_password.html')


# --- ANA SAYFALAR ---
@app.route('/')
@login_required
def index():
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
@login_required
def dashboard():
    db = get_db()
    cursor = db.cursor()
    today = datetime.now()

    active_personnel_count = cursor.execute("SELECT COUNT(id) FROM calisanlar WHERE (isten_cikis_tarihi IS NULL OR isten_cikis_tarihi = '') AND onay_durumu = 'Onaylandı'").fetchone()[0]
    blue_collar_count = cursor.execute("SELECT COUNT(id) FROM calisanlar WHERE yaka_tipi = 'MAVİ YAKA' AND (isten_cikis_tarihi IS NULL OR isten_cikis_tarihi = '') AND onay_durumu = 'Onaylandı'").fetchone()[0]
    white_collar_count = cursor.execute("SELECT COUNT(id) FROM calisanlar WHERE yaka_tipi = 'BEYAZ YAKA' AND (isten_cikis_tarihi IS NULL OR isten_cikis_tarihi = '') AND onay_durumu = 'Onaylandı'").fetchone()[0]
    pending_leave_requests_count = cursor.execute("SELECT COUNT(id) FROM izin_talepleri WHERE durum = 'Beklemede'").fetchone()[0]

    departures_this_month = 0
    all_departures = cursor.execute("SELECT isten_cikis_tarihi FROM calisanlar WHERE isten_cikis_tarihi IS NOT NULL AND isten_cikis_tarihi != '' AND onay_durumu = 'Onaylandı'").fetchall()
    for row in all_departures:
        try:
            dep_date = datetime.strptime(row['isten_cikis_tarihi'], '%Y-%m-%d')
            if dep_date.month == today.month and dep_date.year == today.year:
                departures_this_month += 1
        except (ValueError, TypeError): continue
    turnover_rate = round((departures_this_month / active_personnel_count) * 100, 2) if active_personnel_count > 0 else 0

    company_data = cursor.execute("SELECT s.sube_adi, COUNT(c.id) as count FROM calisanlar c JOIN subeler s ON c.sube_id = s.id WHERE (c.isten_cikis_tarihi IS NULL OR c.isten_cikis_tarihi = '') AND c.onay_durumu = 'Onaylandı' GROUP BY s.sube_adi").fetchall()
    position_data = cursor.execute("SELECT g.gorev_adi, COUNT(c.id) as count FROM calisanlar c JOIN gorevler g ON c.gorev_id = g.id WHERE (c.isten_cikis_tarihi IS NULL OR c.isten_cikis_tarihi = '') AND c.onay_durumu = 'Onaylandı' GROUP BY g.gorev_adi").fetchall()

    long_service_employees = []
    all_active_personnel = cursor.execute("SELECT id, ad_soyad, ise_baslama_tarihi FROM calisanlar WHERE (isten_cikis_tarihi IS NULL OR isten_cikis_tarihi = '') AND onay_durumu = 'Onaylandı'").fetchall()
    for p in all_active_personnel:
        try:
            hire_date = datetime.strptime(p['ise_baslama_tarihi'], '%Y-%m-%d')
            if (today - hire_date).days / 365.25 >= 5:
                long_service_employees.append(p)
        except (ValueError, TypeError): continue

    missing_docs_personnel = cursor.execute("SELECT c.id, c.ad_soyad, (SELECT COUNT(id) FROM evraklar WHERE calisan_id = c.id AND yuklendi_mi = 1) as yuklenen_evrak, (SELECT COUNT(id) FROM evraklar WHERE calisan_id = c.id) as toplam_evrak FROM calisanlar c WHERE (c.isten_cikis_tarihi IS NULL OR c.isten_cikis_tarihi = '') AND c.onay_durumu = 'Onaylandı' AND (SELECT COUNT(id) FROM evraklar WHERE calisan_id = c.id AND yuklendi_mi = 1) < (SELECT COUNT(id) FROM evraklar WHERE calisan_id = c.id) ORDER BY yuklenen_evrak ASC LIMIT 10").fetchall()

    probation_period_days = 60
    thirty_days_later = (today + timedelta(days=30)).strftime('%Y-%m-%d')
    today_str = today.strftime('%Y-%m-%d')
    probation_ending_personnel = cursor.execute("SELECT id, ad_soyad, ise_baslama_tarihi, DATE(ise_baslama_tarihi, '+' || ? || ' days') as probation_end_date FROM calisanlar WHERE (isten_cikis_tarihi IS NULL OR isten_cikis_tarihi = '') AND onay_durumu = 'Onaylandı' AND probation_end_date BETWEEN ? AND ? ORDER BY probation_end_date ASC", (str(probation_period_days), today_str, thirty_days_later)).fetchall()

    dashboard_data = {
        "kpi": {"active_personnel": active_personnel_count, "blue_collar": blue_collar_count, "white_collar": white_collar_count, "departures": departures_this_month, "turnover_rate": turnover_rate, "pending_leave_requests": pending_leave_requests_count},
        "company_chart": {"labels": [row['sube_adi'] for row in company_data], "data": [row['count'] for row in company_data]},
        "position_chart": {"labels": [row['gorev_adi'] for row in position_data], "data": [row['count'] for row in position_data]},
        "long_service_employees": long_service_employees,
        "missing_docs_personnel": missing_docs_personnel,
        "probation_ending_personnel": probation_ending_personnel
    }
    return render_template('dashboard.html', data=dashboard_data)

@app.route('/profile')
@login_required
@personnel_linked_required
def profile():
    db = get_db()
    calisan_id = session.get('calisan_id')

    personnel_info = db.execute("SELECT c.*, s.sube_adi, g.gorev_adi FROM calisanlar c LEFT JOIN subeler s ON c.sube_id = s.id LEFT JOIN gorevler g ON c.gorev_id = g.id WHERE c.id = ?", (calisan_id,)).fetchone()
    my_requests = db.execute('SELECT * FROM izin_talepleri WHERE calisan_id = ? ORDER BY talep_tarihi DESC', (calisan_id,)).fetchall()
    my_team = []

    if session.get('role') in ['admin', 'manager']:
        my_team = db.execute("SELECT c.id, c.ad_soyad, g.gorev_adi FROM calisanlar c LEFT JOIN gorevler g ON c.gorev_id = g.id WHERE c.yonetici_id = ? AND c.onay_durumu = 'Onaylandı'", (calisan_id,)).fetchall()

    return render_template('profile.html', personnel=personnel_info, my_requests=my_requests, my_team=my_team)

# --- PERSONEL YÖNETİMİ ---
@app.route('/personnel')
@login_required
def personnel_list():
    search_query = request.args.get('q')
    yaka_tipi = request.args.get('yaka_tipi')
    durum = request.args.get('durum', 'aktif') 
    db = get_db()

    base_query = "SELECT c.*, s.sube_adi, g.gorev_adi, (SELECT COUNT(id) FROM evraklar WHERE calisan_id = c.id AND yuklendi_mi = 1) as yuklenen_evrak, (SELECT COUNT(id) FROM evraklar WHERE calisan_id = c.id) as toplam_evrak FROM calisanlar c LEFT JOIN subeler s ON c.sube_id = s.id LEFT JOIN gorevler g ON c.gorev_id = g.id"
    conditions = ["c.onay_durumu = 'Onaylandı'"] 
    params = []

    active_filter_text = "Aktif Çalışanlar" 

    if search_query:
        conditions.append("(c.ad_soyad LIKE ? OR c.sicil_no LIKE ?)")
        params.extend([f'%{search_query}%', f'%{search_query}%'])
    if yaka_tipi:
        conditions.append("c.yaka_tipi = ?")
        params.append(yaka_tipi)
        active_filter_text = yaka_tipi.replace("_", " ").title()

    if durum == 'ayrilan':
        conditions.append("c.isten_cikis_tarihi IS NOT NULL AND c.isten_cikis_tarihi != ''")
        active_filter_text = "Ayrılan Personeller"
    else: 
        conditions.append("(c.isten_cikis_tarihi IS NULL OR c.isten_cikis_tarihi = '')")

    base_query += " WHERE " + " AND ".join(conditions)
    base_query += " ORDER BY c.id DESC"
    calisanlar = db.execute(base_query, params).fetchall()
    return render_template('personnel_list.html', calisanlar=calisanlar, active_filter=active_filter_text)

@app.route('/personnel/export/<string:file_type>')
@login_required
def export_personnel(file_type):
    flash(f"{file_type.capitalize()} olarak dışa aktarma özelliği henüz tamamlanmadı.", "info")
    return redirect(url_for('personnel_list'))

@app.route('/personnel/add', methods=['GET', 'POST'])
@login_required
def add_personnel():
    if session.get('role') not in ['admin', 'manager']:
        flash("Bu işlemi yapma yetkiniz yok.", "danger")
        return redirect(url_for('personnel_list'))

    db = get_db()
    if request.method == 'POST':
        tc_kimlik = request.form.get('tc_kimlik')
        if not tc_kimlik or db.execute('SELECT id FROM calisanlar WHERE tc_kimlik = ?', (tc_kimlik,)).fetchone():
            flash("Geçerli bir TC Kimlik Numarası girilmelidir ve bu TC zaten kullanımda olmamalıdır.", 'danger')
            return redirect(url_for('add_personnel'))

        onay_durumu = 'Onaylandı' if session.get('role') == 'admin' else 'Onay Bekliyor'

        cursor = db.cursor()
        cursor.execute("INSERT INTO calisanlar (ad_soyad, ise_baslama_tarihi, sicil_no, tc_kimlik, mail, sube_id, gorev_id, tel, yakin_tel, adres, iban, egitim, ucreti, yaka_tipi, yonetici_id, onay_durumu) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (request.form.get('ad_soyad'), request.form.get('ise_baslama_tarihi'), request.form.get('sicil_no'), tc_kimlik, request.form.get('mail'), request.form.get('sube_id'), request.form.get('gorev_id'), request.form.get('tel'), request.form.get('yakin_tel'), request.form.get('adres'), request.form.get('iban'), request.form.get('egitim'), request.form.get('ucreti'), request.form.get('yaka_tipi'), request.form.get('yonetici_id'), onay_durumu))
        new_id = cursor.lastrowid

        if onay_durumu == 'Onaylandı':
            default_password = generate_random_password(8)
            hashed_password = generate_password_hash(default_password)
            cursor.execute("INSERT INTO kullanicilar (password, role, calisan_id) VALUES (?, ?, ?)", (hashed_password, 'user', new_id))

            email_sent = send_password_email(request.form.get('mail'), default_password)
            message = f"Personel eklendi ve kullanıcı hesabı oluşturuldu. Yönetici notu için şifre: {default_password}"
            if email_sent:
                flash(f"{message} (Şifre ayrıca personele e-posta ile gönderildi.)", 'success')
            else:
                flash(f"{message} (E-posta ayarları yanlış olduğu için e-posta gönderilemedi.)", 'warning')
        else:
            flash("Yeni personel kaydı oluşturuldu ve yönetici onayına gönderildi.", 'success')

        for evrak in GEREKLI_EVRAKLAR:
            cursor.execute('INSERT INTO evraklar (calisan_id, evrak_tipi) VALUES (?, ?)', (new_id, evrak))

        db.commit()
        return redirect(url_for('personnel_list'))

    potential_managers = db.execute('SELECT id, ad_soyad FROM calisanlar WHERE onay_durumu="Onaylandı" ORDER BY ad_soyad').fetchall()
    subeler = db.execute('SELECT * FROM subeler ORDER BY sube_adi').fetchall()
    gorevler = db.execute('SELECT * FROM gorevler ORDER BY gorev_adi').fetchall()
    return render_template('add_personnel.html', managers=potential_managers, subeler=subeler, gorevler=gorevler)

@app.route('/personnel/manage/<int:calisan_id>')
@login_required
def manage_personnel(calisan_id):
    db = get_db()
    calisan = db.execute("SELECT c.*, s.sube_adi, g.gorev_adi FROM calisanlar c LEFT JOIN subeler s ON c.sube_id = s.id LEFT JOIN gorevler g ON c.gorev_id = g.id WHERE c.id = ?", (calisan_id,)).fetchone()

    if not calisan or (calisan['onay_durumu'] != 'Onaylandı' and session.get('role') != 'admin'):
        flash("Bu personele erişim yetkiniz yok veya personel henüz onaylanmadı.", "danger")
        return redirect(url_for('personnel_list'))

    evraklar = db.execute('SELECT * FROM evraklar WHERE calisan_id = ?', (calisan_id,)).fetchall()
    potential_managers = db.execute('SELECT id, ad_soyad, sicil_no FROM calisanlar WHERE id != ? AND onay_durumu="Onaylandı" ORDER BY ad_soyad', (calisan_id,)).fetchall()
    subeler = db.execute('SELECT * FROM subeler ORDER BY sube_adi').fetchall()
    gorevler = db.execute('SELECT * FROM gorevler ORDER BY gorev_adi').fetchall()

    return render_template('personnel_manage.html', calisan=calisan, evraklar=evraklar, managers=potential_managers, subeler=subeler, gorevler=gorevler)

@app.route('/personnel/update/<int:calisan_id>', methods=['POST'])
@login_required
@admin_required
def update_personnel(calisan_id):
    db = get_db()
    form = request.form
    yonetici_id = form.get('yonetici_id') if form.get('yonetici_id') else None

    db.execute("UPDATE calisanlar SET ad_soyad=?, ise_baslama_tarihi=?, sicil_no=?, tc_kimlik=?, mail=?, sube_id=?, gorev_id=?, tel=?, yakin_tel=?, adres=?, iban=?, egitim=?, ucreti=?, aciklama=?, yaka_tipi=?, isten_cikis_tarihi=?, yonetici_id=? WHERE id = ?",
        (form.get('ad_soyad'), form.get('ise_baslama_tarihi'), form.get('sicil_no'), form.get('tc_kimlik'), form.get('mail'), form.get('sube_id'), form.get('gorev_id'), form.get('tel'), form.get('yakin_tel'), form.get('adres'), form.get('iban'), form.get('egitim'), form.get('ucreti'), form.get('aciklama'), form.get('yaka_tipi'), form.get('isten_cikis_tarihi'), yonetici_id, calisan_id))
    db.commit()
    flash('Personel bilgileri başarıyla güncellendi.', 'success')
    return redirect(url_for('manage_personnel', calisan_id=calisan_id))

@app.route('/personnel/delete/<int:calisan_id>', methods=['POST'])
@login_required
@admin_required
def delete_personnel(calisan_id):
    db = get_db()
    files = db.execute('SELECT dosya_yolu FROM evraklar WHERE calisan_id = ? AND dosya_yolu IS NOT NULL', (calisan_id,)).fetchall()
    for file in files:
        try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'], file['dosya_yolu']))
        except OSError: pass
    db.execute('DELETE FROM calisanlar WHERE id = ?', (calisan_id,))
    db.commit()
    flash('Personel ve ilişkili hesapları kalıcı olarak silindi.', 'success')
    return redirect(url_for('personnel_list'))

@app.route('/personnel/upload/<int:calisan_id>/<evrak_tipi>', methods=['POST'])
@login_required
def upload_file(calisan_id, evrak_tipi):
    file = request.files.get('file')
    if not file or not file.filename or not allowed_file(file.filename):
        flash('Geçersiz dosya.', 'warning')
        return redirect(url_for('manage_personnel', calisan_id=calisan_id))
    filename = f"{calisan_id}_{evrak_tipi.replace(' ', '_')}_{secure_filename(file.filename)}"
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    db = get_db()
    db.execute('UPDATE evraklar SET dosya_yolu = ?, yuklendi_mi = 1 WHERE calisan_id = ? AND evrak_tipi = ?', (filename, calisan_id, evrak_tipi))
    db.commit()
    flash(f"'{evrak_tipi}' yüklendi.", 'success')
    return redirect(url_for('manage_personnel', calisan_id=calisan_id))

@app.route('/uploads/<filename>')
@login_required
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# --- YÖNETİCİ ONAY MEKANİZMASI ---
@app.route('/approvals')
@login_required
@admin_required
def approval_list():
    db = get_db()
    personnel = db.execute("SELECT * FROM calisanlar WHERE onay_durumu = 'Onay Bekliyor' ORDER BY id DESC").fetchall()
    return render_template('approval_list.html', personnel=personnel)

@app.route('/approvals/<int:personnel_id>')
@login_required
@admin_required
def approval_detail(personnel_id):
    db = get_db()
    personnel = db.execute("SELECT * FROM calisanlar WHERE id = ? AND onay_durumu = 'Onay Bekliyor'", (personnel_id,)).fetchone()
    if not personnel:
        flash("Onay bekleyen böyle bir personel bulunamadı.", "warning")
        return redirect(url_for('approval_list'))

    evraklar = db.execute("SELECT evrak_tipi FROM evraklar WHERE calisan_id = ?", (personnel_id,)).fetchall()
    return render_template('approval_detail.html', personnel=personnel, evraklar=evraklar)

@app.route('/approvals/process/<int:personnel_id>', methods=['POST'])
@login_required
@admin_required
def process_approval(personnel_id):
    db = get_db()
    action = request.form.get('action')
    admin_notu = request.form.get('admin_notu')

    if action == 'approve':
        db.execute("UPDATE calisanlar SET onay_durumu = 'Onaylandı', admin_notu = ? WHERE id = ?", (admin_notu or 'Onaylandı.', personnel_id))

        default_password = generate_random_password(8)
        hashed_password = generate_password_hash(default_password)
        db.execute("INSERT INTO kullanicilar (password, role, calisan_id) VALUES (?, ?, ?)", (hashed_password, 'user', personnel_id))

        personnel = db.execute("SELECT * FROM calisanlar WHERE id = ?", (personnel_id,)).fetchone()
        email_sent = send_password_email(personnel['mail'], default_password)

        message = f"Personel kaydı onaylandı ve kullanıcı hesabı oluşturuldu. Şifre: {default_password}"
        if email_sent:
            flash(f"{message} (Şifre personele e-posta ile gönderildi.)", 'success')
        else:
            flash(f"{message} (E-posta gönderilemedi.)", 'warning')

    elif action == 'reject':
        if not admin_notu:
            flash("Reddetme işlemi için bir neden belirtmek zorunludur.", "danger")
            return redirect(url_for('approval_detail', personnel_id=personnel_id))

        db.execute("UPDATE calisanlar SET onay_durumu = 'Reddedildi', admin_notu = ? WHERE id = ?", (admin_notu, personnel_id))
        flash("Personel kaydı reddedildi.", "info")

    db.commit()
    return redirect(url_for('approval_list'))


# --- KULLANICI YÖNETİMİ (ADMİN) ---
@app.route('/users')
@login_required
@admin_required
def user_management():
    db = get_db()
    requests = db.execute("SELECT COUNT(id) FROM sifre_sifirlama_talepleri WHERE durum = 'Beklemede'").fetchone()[0]
    users = db.execute("SELECT u.id, u.role, c.ad_soyad, c.tc_kimlik FROM kullanicilar u JOIN calisanlar c ON u.calisan_id = c.id ORDER BY c.ad_soyad").fetchall()
    unlinked_personnel = db.execute("SELECT * FROM calisanlar WHERE id NOT IN (SELECT calisan_id FROM kullanicilar WHERE calisan_id IS NOT NULL) AND onay_durumu = 'Onaylandı'").fetchall()
    return render_template('user_management.html', users=users, password_requests_count=requests, unlinked_personnel=unlinked_personnel)

@app.route('/users/add', methods=['POST'])
@login_required
@admin_required
def add_user():
    db = get_db()
    calisan_id = request.form.get('calisan_id')
    if not calisan_id:
        flash("Lütfen bir personel seçin.", "danger")
        return redirect(url_for('user_management'))

    existing_user = db.execute("SELECT id FROM kullanicilar WHERE calisan_id = ?", (calisan_id,)).fetchone()
    if existing_user:
        flash("Seçilen personel için zaten bir kullanıcı hesabı mevcut.", "warning")
        return redirect(url_for('user_management'))

    role = request.form.get('role', 'user')
    default_password = generate_random_password(8)
    hashed_password = generate_password_hash(default_password)

    db.execute("INSERT INTO kullanicilar (password, role, calisan_id) VALUES (?, ?, ?)", (hashed_password, role, calisan_id))
    db.commit()
    flash(f"Personele başarıyla kullanıcı hesabı oluşturuldu. İletilmesi gereken şifre: {default_password}", "success")
    return redirect(url_for('user_management'))

@app.route('/users/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    db = get_db()
    user = db.execute("SELECT u.id, u.role, c.ad_soyad, c.mail, c.id as calisan_id FROM kullanicilar u JOIN calisanlar c ON u.calisan_id = c.id WHERE u.id = ?", (user_id,)).fetchone()

    if not user:
        flash("Kullanıcı bulunamadı.", "danger")
        return redirect(url_for('user_management'))

    if request.method == 'POST':
        new_role = request.form.get('role')
        if user_id == session.get('user_id') and new_role != session.get('role'):
            flash('Kendi yetkinizi değiştiremezsiniz.', 'danger')
            return redirect(url_for('edit_user', user_id=user_id))

        db.execute("UPDATE kullanicilar SET role = ? WHERE id = ?", (new_role, user_id))
        db.commit()
        flash(f"'{user['ad_soyad']}' adlı kullanıcının yetkisi güncellendi.", "success")
        return redirect(url_for('user_management'))

    return render_template('edit_user.html', user=user)

@app.route('/users/delete/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    if user_id == session['user_id']:
        flash('Kendi hesabınızı silemezsiniz.', 'danger')
        return redirect(url_for('user_management'))
    db = get_db()
    user_to_delete = db.execute("SELECT * FROM kullanicilar WHERE id=?",(user_id,)).fetchone()
    if not user_to_delete:
        flash("Silinecek kullanıcı bulunamadı.", "danger")
        return redirect(url_for('user_management'))

    db.execute('DELETE FROM kullanicilar WHERE id = ?', (user_id,))
    db.commit()
    flash('Kullanıcı hesabı başarıyla silindi. Personel kaydı silinmedi.', 'success')
    return redirect(url_for('user_management'))

@app.route('/users/generate_password/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def generate_new_password(user_id):
    db = get_db()
    user = db.execute("SELECT * FROM kullanicilar WHERE id = ?", (user_id,)).fetchone()
    if not user:
        flash("Kullanıcı bulunamadı.", "danger")
        return redirect(url_for('user_management'))

    personnel = db.execute("SELECT * FROM calisanlar WHERE id = ?", (user['calisan_id'],)).fetchone()
    if not personnel:
        flash("Kullanıcıya bağlı personel kaydı bulunamadı.", "danger")
        return redirect(url_for('edit_user', user_id=user_id))

    new_password = generate_random_password()
    hashed_password = generate_password_hash(new_password)

    db.execute("UPDATE kullanicilar SET password = ? WHERE id = ?", (hashed_password, user_id))
    db.commit()

    email_sent = False
    if personnel['mail']:
        email_sent = send_password_email(personnel['mail'], new_password)

    return render_template('show_password.html', 
                           personnel_name=personnel['ad_soyad'], 
                           new_password=new_password, 
                           email_sent=email_sent,
                           user_id=user_id)

@app.route('/password_requests')
@login_required
@admin_required
def password_requests():
    db = get_db()
    requests = db.execute("SELECT sst.id, sst.talep_tarihi, c.ad_soyad, c.sicil_no, c.tc_kimlik FROM sifre_sifirlama_talepleri sst JOIN calisanlar c ON sst.calisan_id = c.id WHERE sst.durum = 'Beklemede' ORDER BY sst.talep_tarihi DESC").fetchall()
    return render_template('password_requests.html', requests=requests)

@app.route('/reset_password/<int:request_id>', methods=['POST'])
@login_required
@admin_required
def reset_password(request_id):
    db = get_db()
    req = db.execute("SELECT * FROM sifre_sifirlama_talepleri WHERE id = ?", (request_id,)).fetchone()

    if not req:
        flash("Geçersiz şifre sıfırlama talebi.", "danger")
        return redirect(url_for('password_requests'))

    personnel = db.execute("SELECT * FROM calisanlar WHERE id = ?", (req['calisan_id'],)).fetchone()
    if not personnel or not personnel['mail']:
        flash("Personelin sistemde kayıtlı bir e-posta adresi bulunamadığı için işlem yapılamıyor.", "danger")
        return redirect(url_for('password_requests'))

    new_password = generate_random_password()
    hashed_password = generate_password_hash(new_password)

    db.execute("UPDATE kullanicilar SET password = ? WHERE calisan_id = ?", (hashed_password, req['calisan_id']))
    db.execute("UPDATE sifre_sifirlama_talepleri SET durum = 'Tamamlandı' WHERE id = ?", (request_id,))
    db.commit()

    if send_password_email(personnel['mail'], new_password):
        flash(f"{personnel['ad_soyad']} adlı personelin şifresi başarıyla sıfırlandı ve e-posta ile gönderildi.", "success")
    else:
        flash(f"Şifre başarıyla sıfırlandı ancak e-posta gönderilirken bir hata oluştu. Lütfen şifreyi ({new_password}) personele manuel olarak iletin.", "warning")

    return redirect(url_for('password_requests'))


# --- İZİN YÖNETİMİ ---
@app.route('/leave', methods=['GET', 'POST'])
@login_required
@personnel_linked_required
def leave_management():
    db = get_db()
    calisan_id = session.get('calisan_id')
    user_role = session.get('role')

    if request.method == 'POST':
        start_date_str = request.form['baslangic_tarihi']
        end_date_str = request.form['bitis_tarihi']
        leave_type = request.form['izin_tipi']
        aciklama = request.form['aciklama']
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
            if start_date > end_date:
                flash("Başlangıç tarihi, bitiş tarihinden sonra olamaz.", "danger")
                return redirect(url_for('leave_management'))
        except ValueError:
            flash("Geçersiz tarih formatı.", "danger")
            return redirect(url_for('leave_management'))
        day_diff = (end_date - start_date).days + 1
        current_personnel = db.execute('SELECT * FROM calisanlar WHERE id = ?', (calisan_id,)).fetchone()
        if leave_type == 'Yıllık İzin':
            if current_personnel['yillik_izin_bakiye'] < day_diff:
                flash(f"Yetersiz izin bakiyesi. Kalan izin: {current_personnel['yillik_izin_bakiye']} gün.", "danger")
                return redirect(url_for('leave_management'))
            new_balance = current_personnel['yillik_izin_bakiye'] - day_diff
            db.execute('UPDATE calisanlar SET yillik_izin_bakiye = ? WHERE id = ?', (new_balance, calisan_id))
        db.execute("INSERT INTO izin_talepleri (calisan_id, izin_tipi, baslangic_tarihi, bitis_tarihi, gun_sayisi, aciklama, talep_tarihi) VALUES (?, ?, ?, ?, ?, ?, ?)", (calisan_id, leave_type, start_date_str, end_date_str, day_diff, aciklama, datetime.now().strftime('%Y-%m-%d')))
        db.commit()
        flash("İzin talebiniz başarıyla alınmıştır.", "success")
        return redirect(url_for('leave_management'))

    pending_requests = []
    if user_role == 'admin':
        pending_requests = db.execute("SELECT it.*, c.ad_soyad FROM izin_talepleri it JOIN calisanlar c ON it.calisan_id = c.id WHERE it.durum = 'Beklemede' ORDER BY it.talep_tarihi DESC").fetchall()
    elif user_role == 'manager':
        manager_personnel_id = session.get('calisan_id')
        if manager_personnel_id:
             pending_requests = db.execute("SELECT it.*, c.ad_soyad FROM izin_talepleri it JOIN calisanlar c ON it.calisan_id = c.id WHERE it.durum = 'Beklemede' AND c.yonetici_id = ? ORDER BY it.talep_tarihi DESC", (manager_personnel_id,)).fetchall()

    return render_template('leave_management.html', pending_requests=pending_requests)

@app.route('/leave/action/<int:request_id>/<string:action>', methods=['POST'])
@login_required
def leave_action(request_id, action):
    if session.get('role') not in ['admin', 'manager']:
        flash("Bu işlemi yapma yetkiniz yok.", "danger")
        return redirect(url_for('leave_management'))
    db = get_db()
    leave_request = db.execute('SELECT * FROM izin_talepleri WHERE id = ?', (request_id,)).fetchone()
    if not leave_request:
        flash("İzin talebi bulunamadı.", "danger")
        return redirect(url_for('leave_management'))
    if action == 'approve':
        db.execute("UPDATE izin_talepleri SET durum = 'Onaylandı' WHERE id = ?", (request_id,))
        flash("İzin talebi onaylandı.", "success")
    elif action == 'reject':
        db.execute("UPDATE izin_talepleri SET durum = 'Reddedildi' WHERE id = ?", (request_id,))
        if leave_request['izin_tipi'] == 'Yıllık İzin':
            db.execute("UPDATE calisanlar SET yillik_izin_bakiye = yillik_izin_bakiye + ? WHERE id = ?", (leave_request['gun_sayisi'], leave_request['calisan_id']))
        flash("İzin talebi reddedildi.", "info")
    db.commit()
    return redirect(url_for('leave_management'))


# --- PERFORMANS YÖNETİMİ ---
@app.route('/performance', methods=['GET', 'POST'])
@login_required
@admin_required
def performance_management():
    db = get_db()
    if request.method == 'POST':
        donem_adi = request.form.get('donem_adi')
        baslangic_tarihi = request.form.get('baslangic_tarihi')
        bitis_tarihi = request.form.get('bitis_tarihi')
        if not donem_adi or not baslangic_tarihi or not bitis_tarihi:
            flash("Tüm alanlar zorunludur.", "danger")
        else:
            db.execute("INSERT INTO degerlendirme_donemleri (donem_adi, baslangic_tarihi, bitis_tarihi) VALUES (?, ?, ?)", (donem_adi, baslangic_tarihi, bitis_tarihi))
            db.commit()
            flash(f"'{donem_adi}' adlı değerlendirme dönemi başarıyla oluşturuldu.", "success")
        return redirect(url_for('performance_management'))

    periods = db.execute("SELECT * FROM degerlendirme_donemleri ORDER BY baslangic_tarihi DESC").fetchall()
    return render_template('performance_management.html', periods=periods)

@app.route('/performance/period/<int:period_id>', methods=['GET', 'POST'])
@login_required
@personnel_linked_required
def performance_period_detail(period_id):
    if session.get('role') not in ['admin', 'manager']:
        flash("Bu sayfaya erişim yetkiniz yok.", "danger")
        return redirect(url_for('dashboard'))

    db = get_db()
    period = db.execute('SELECT * FROM degerlendirme_donemleri WHERE id = ?', (period_id,)).fetchone()
    if not period:
        return "Dönem bulunamadı", 404

    if request.method == 'POST':
        calisan_id = request.form.get('calisan_id')
        hedef_aciklamasi = request.form.get('hedef_aciklamasi')
        agirlik = request.form.get('agirlik', 100)

        if not calisan_id or not hedef_aciklamasi:
            flash("Personel ve Hedef Açıklaması alanları zorunludur.", "danger")
        else:
            db.execute("INSERT INTO personel_hedefleri (calisan_id, donem_id, hedef_aciklamasi, agirlik) VALUES (?, ?, ?, ?)", (calisan_id, period_id, hedef_aciklamasi, agirlik))
            db.commit()
            flash("Yeni hedef başarıyla eklendi.", "success")
        return redirect(url_for('performance_period_detail', period_id=period_id))

    employees_to_manage = []
    if session.get('role') == 'admin':
        employees_to_manage = db.execute("SELECT id, ad_soyad, sicil_no FROM calisanlar WHERE isten_cikis_tarihi IS NULL OR isten_cikis_tarihi = '' ORDER BY ad_soyad").fetchall()
    elif session.get('role') == 'manager':
        employees_to_manage = db.execute("SELECT id, ad_soyad, sicil_no FROM calisanlar WHERE (isten_cikis_tarihi IS NULL OR isten_cikis_tarihi = '') AND yonetici_id = ? ORDER BY ad_soyad", (session.get('calisan_id'),)).fetchall()

    targets = db.execute("SELECT ph.*, c.ad_soyad FROM personel_hedefleri ph JOIN calisanlar c ON ph.calisan_id = c.id WHERE ph.donem_id = ? ORDER BY c.ad_soyad", (period_id,)).fetchall()

    return render_template('performance_period_detail.html', period=period, employees=employees_to_manage, targets=targets)

@app.route('/performance/target/delete/<int:target_id>', methods=['POST'])
@login_required
def delete_target(target_id):
    if session.get('role') not in ['admin', 'manager']:
        flash("Bu işlemi yapma yetkiniz yok.", "danger")
        return redirect(url_for('dashboard'))

    db = get_db()
    target = db.execute("SELECT * FROM personel_hedefleri WHERE id = ?", (target_id,)).fetchone()

    if not target:
        flash("Silinecek hedef bulunamadı.", "danger")
        return redirect(url_for('performance_management'))

    if session.get('role') == 'manager':
        personnel = db.execute("SELECT yonetici_id FROM calisanlar WHERE id = ?", (target['calisan_id'],)).fetchone()
        if not personnel or personnel['yonetici_id'] != session.get('calisan_id'):
            flash("Sadece kendi ekibinizdeki personelin hedeflerini silebilirsiniz.", "danger")
            return redirect(url_for('performance_period_detail', period_id=target['donem_id']))

    period_id = target['donem_id']
    db.execute("DELETE FROM personel_hedefleri WHERE id = ?", (target_id,))
    db.commit()
    flash("Hedef başarıyla silindi.", "success")

    return redirect(url_for('performance_period_detail', period_id=period_id))

# --- MAIN EXECUTION ---
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)