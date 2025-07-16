from flask import Flask, render_template, request, redirect, url_for, g, flash, send_from_directory, session, make_response
import sqlite3
import os
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from database import init_db, GEREKLI_EVRAKLAR
from datetime import datetime, timedelta
from functools import wraps
import io
import openpyxl
from fpdf import FPDF

# --- Uygulama Ayarları ---
DATABASE = 'hr.db'
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}

app = Flask(__name__)
app.secret_key = 'bu-cok-gizli-bir-anahtar-olmalı-ve-degistirilmeli'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- Veritabanı Bağlantı Yönetimi ---
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
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- YETKİLENDİRME DECORATOR'LARI ---
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

# --- Rotalar (Sayfalar) ---
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

    active_personnel_count = cursor.execute("SELECT COUNT(*) FROM calisanlar WHERE isten_cikis_tarihi IS NULL OR isten_cikis_tarihi = ''").fetchone()[0]
    blue_collar_count = cursor.execute("SELECT COUNT(*) FROM calisanlar WHERE yaka_tipi = 'MAVİ YAKA' AND (isten_cikis_tarihi IS NULL OR isten_cikis_tarihi = '')").fetchone()[0]
    white_collar_count = cursor.execute("SELECT COUNT(*) FROM calisanlar WHERE yaka_tipi = 'BEYAZ YAKA' AND (isten_cikis_tarihi IS NULL OR isten_cikis_tarihi = '')").fetchone()[0]
    pending_leave_requests_count = cursor.execute("SELECT COUNT(*) FROM izin_talepleri WHERE durum = 'Beklemede'").fetchone()[0]

    departures_this_month = 0
    all_departures = cursor.execute("SELECT isten_cikis_tarihi FROM calisanlar WHERE isten_cikis_tarihi IS NOT NULL AND isten_cikis_tarihi != ''").fetchall()
    for row in all_departures:
        try:
            dep_date = datetime.strptime(row['isten_cikis_tarihi'], '%Y-%m-%d')
            if dep_date.month == today.month and dep_date.year == today.year:
                departures_this_month += 1
        except (ValueError, TypeError): continue
    turnover_rate = round((departures_this_month / active_personnel_count) * 100, 2) if active_personnel_count > 0 else 0

    company_data = cursor.execute("SELECT sube, COUNT(*) as count FROM calisanlar WHERE (isten_cikis_tarihi IS NULL OR isten_cikis_tarihi = '') AND sube IS NOT NULL GROUP BY sube").fetchall()
    position_data = cursor.execute("SELECT gorevi, COUNT(*) as count FROM calisanlar WHERE (isten_cikis_tarihi IS NULL OR isten_cikis_tarihi = '') AND gorevi IS NOT NULL GROUP BY gorevi").fetchall()

    long_service_employees = []
    all_active_personnel = cursor.execute("SELECT id, ad_soyad, ise_baslama_tarihi FROM calisanlar WHERE isten_cikis_tarihi IS NULL OR isten_cikis_tarihi = ''").fetchall()
    for p in all_active_personnel:
        try:
            hire_date = datetime.strptime(p['ise_baslama_tarihi'], '%Y-%m-%d')
            if (today - hire_date).days / 365.25 >= 5:
                long_service_employees.append(p)
        except (ValueError, TypeError): continue

    missing_docs_personnel = cursor.execute("""
        SELECT c.id, c.ad_soyad,
               (SELECT COUNT(*) FROM evraklar WHERE calisan_id = c.id AND yuklendi_mi = 1) as yuklenen_evrak,
               (SELECT COUNT(*) FROM evraklar WHERE calisan_id = c.id) as toplam_evrak
        FROM calisanlar c
        WHERE (c.isten_cikis_tarihi IS NULL OR c.isten_cikis_tarihi = '')
        AND (SELECT COUNT(*) FROM evraklar WHERE calisan_id = c.id AND yuklendi_mi = 1) < (SELECT COUNT(*) FROM evraklar WHERE calisan_id = c.id)
        ORDER BY yuklenen_evrak ASC LIMIT 10
    """).fetchall()

    probation_period_days = 60
    thirty_days_later = (today + timedelta(days=30)).strftime('%Y-%m-%d')
    today_str = today.strftime('%Y-%m-%d')
    probation_ending_personnel = cursor.execute("""
        SELECT id, ad_soyad, ise_baslama_tarihi,
               DATE(ise_baslama_tarihi, '+' || ? || ' days') as probation_end_date
        FROM calisanlar
        WHERE (isten_cikis_tarihi IS NULL OR isten_cikis_tarihi = '')
        AND probation_end_date BETWEEN ? AND ?
        ORDER BY probation_end_date ASC
    """, (str(probation_period_days), today_str, thirty_days_later)).fetchall()

    dashboard_data = {
        "kpi": {"active_personnel": active_personnel_count, "blue_collar": blue_collar_count, "white_collar": white_collar_count, "departures": departures_this_month, "turnover_rate": turnover_rate, "pending_leave_requests": pending_leave_requests_count},
        "company_chart": {"labels": [row['sube'] for row in company_data if row['sube']], "data": [row['count'] for row in company_data if row['sube']]},
        "position_chart": {"labels": [row['gorevi'] for row in position_data if row['gorevi']], "data": [row['count'] for row in position_data if row['gorevi']]},
        "long_service_employees": long_service_employees,
        "missing_docs_personnel": missing_docs_personnel,
        "probation_ending_personnel": probation_ending_personnel
    }
    return render_template('dashboard.html', data=dashboard_data)

class PDF(FPDF):
    def header(self):
        self.add_font('DejaVu', '', 'DejaVuSans.ttf', uni=True)
        self.set_font('DejaVu', '', 12)
        self.cell(0, 10, 'Personel Listesi Raporu', 0, 1, 'C')
        self.ln(5)
    def footer(self):
        self.set_y(-15)
        self.set_font('DejaVu', '', 8)
        self.cell(0, 10, f'Sayfa {self.page_no()}', 0, 0, 'C')

@app.route('/personnel/export/<string:file_type>')
@login_required
def export_personnel(file_type):
    search_query = request.args.get('q')
    yaka_tipi = request.args.get('yaka_tipi')
    durum = request.args.get('durum')
    db = get_db()
    base_query = "SELECT * FROM calisanlar c"
    conditions = []
    params = []
    if search_query:
        conditions.append("(c.ad_soyad LIKE ? OR c.sicil_no LIKE ?)")
        params.extend([f'%{search_query}%', f'%{search_query}%'])
    if yaka_tipi:
        conditions.append("c.yaka_tipi = ?")
        params.append(yaka_tipi)
    if durum:
        report_date = datetime.now()
        if durum == 'aktif':
            conditions.append("(c.isten_cikis_tarihi IS NULL OR c.isten_cikis_tarihi = '')")
        elif durum == 'ayrilan':
            conditions.append("strftime('%Y-%m', c.isten_cikis_tarihi) = ?")
            params.append(report_date.strftime('%Y-%m'))
    if conditions:
        base_query += " WHERE " + " AND ".join(conditions)
    base_query += " ORDER BY c.ad_soyad ASC"
    personnel_data = db.execute(base_query, params).fetchall()
    if file_type == 'excel':
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "Personel Listesi"
        headers = ["Sicil No", "Adı Soyadı", "TC Kimlik", "Telefon", "Şube", "Görevi", "Yaka Tipi", "İşe Başlama", "İşten Çıkış"]
        sheet.append(headers)
        for person in personnel_data:
            sheet.append([person['sicil_no'], person['ad_soyad'], person['tc_kimlik'], person['tel'], person['sube'], person['gorevi'], person['yaka_tipi'], person['ise_baslama_tarihi'], person['isten_cikis_tarihi']])
        output = io.BytesIO()
        workbook.save(output)
        output.seek(0)
        response = make_response(output.read())
        response.headers['Content-Disposition'] = 'attachment; filename=personel_listesi.xlsx'
        response.headers['Content-type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        return response
    elif file_type == 'pdf':
        pdf = PDF(orientation='L', unit='mm', format='A4')
        pdf.add_page()
        pdf.set_font('DejaVu', '', 8)
        headers = ["Sicil No", "Adı Soyadı", "TC Kimlik", "Telefon", "Şube", "Görevi", "Yaka Tipi", "İşe Başlama"]
        col_widths = [20, 45, 30, 30, 35, 35, 25, 30]
        for i, header in enumerate(headers):
            pdf.cell(col_widths[i], 10, header, 1, 0, 'C')
        pdf.ln()
        for person in personnel_data:
            pdf.cell(col_widths[0], 10, str(person['sicil_no'] or ''), 1)
            pdf.cell(col_widths[1], 10, str(person['ad_soyad'] or ''), 1)
            pdf.cell(col_widths[2], 10, str(person['tc_kimlik'] or ''), 1)
            pdf.cell(col_widths[3], 10, str(person['tel'] or ''), 1)
            pdf.cell(col_widths[4], 10, str(person['sube'] or ''), 1)
            pdf.cell(col_widths[5], 10, str(person['gorevi'] or ''), 1)
            pdf.cell(col_widths[6], 10, str(person['yaka_tipi'] or ''), 1)
            pdf.cell(col_widths[7], 10, str(person['ise_baslama_tarihi'] or ''), 1)
            pdf.ln()
        response = make_response(pdf.output(dest='S').encode('latin-1'))
        response.headers['Content-Disposition'] = 'attachment; filename=personel_listesi.pdf'
        response.headers['Content-type'] = 'application/pdf'
        return response
    return redirect(url_for('personnel_list'))

@app.route('/personnel')
@login_required
def personnel_list():
    search_query = request.args.get('q')
    yaka_tipi = request.args.get('yaka_tipi')
    durum = request.args.get('durum')
    db = get_db()
    base_query = "SELECT c.*, (SELECT COUNT(*) FROM evraklar WHERE calisan_id = c.id AND yuklendi_mi = 1) as yuklenen_evrak, (SELECT COUNT(*) FROM evraklar WHERE calisan_id = c.id) as toplam_evrak FROM calisanlar c"
    conditions = []
    params = []
    active_filter_text = None
    if search_query:
        conditions.append("(c.ad_soyad LIKE ? OR c.sicil_no LIKE ?)")
        params.extend([f'%{search_query}%', f'%{search_query}%'])
    if yaka_tipi:
        conditions.append("c.yaka_tipi = ?")
        params.append(yaka_tipi)
        active_filter_text = yaka_tipi.replace("_", " ").title()
    if durum:
        report_date = datetime.now()
        if durum == 'aktif':
            conditions.append("(c.isten_cikis_tarihi IS NULL OR c.isten_cikis_tarihi = '')")
            active_filter_text = 'Aktif Çalışanlar'
        elif durum == 'ayrilan':
            conditions.append("strftime('%Y-%m', c.isten_cikis_tarihi) = ?")
            params.append(report_date.strftime('%Y-%m'))
            active_filter_text = f"{report_date.strftime('%B')} Ayında Ayrılanlar"
    if conditions:
        base_query += " WHERE " + " AND ".join(conditions)
    base_query += " ORDER BY c.id DESC"
    calisanlar = db.execute(base_query, params).fetchall()
    return render_template('personnel_list.html', calisanlar=calisanlar, active_filter=active_filter_text)

@app.route('/personnel/add', methods=['GET', 'POST'])
@login_required
def add_personnel():
    if request.method == 'POST':
        db = get_db()
        sicil_no = request.form['sicil_no']
        if sicil_no and db.execute('SELECT id FROM calisanlar WHERE sicil_no = ?', (sicil_no,)).fetchone():
            flash(f"'{sicil_no}' sicil numarası zaten kullanımda.", 'danger')
            return render_template('add_personnel.html')
        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO calisanlar (ad_soyad, ise_baslama_tarihi, sicil_no, sube, gorevi, tel, yakin_tel, tc_kimlik, adres, iban, egitim, ucreti, yaka_tipi, yonetici_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (request.form['ad_soyad'], request.form['ise_baslama_tarihi'], sicil_no, request.form['sube'], request.form['gorevi'], request.form['tel'], request.form['yakin_tel'], request.form['tc_kimlik'], request.form['adres'], request.form['iban'], request.form['egitim'], request.form['ucreti'], request.form['yaka_tipi'], request.form.get('yonetici_id'))
        )
        new_id = cursor.lastrowid
        for evrak in GEREKLI_EVRAKLAR:
            cursor.execute('INSERT INTO evraklar (calisan_id, evrak_tipi) VALUES (?, ?)', (new_id, evrak))
        db.commit()
        flash(f"'{request.form['ad_soyad']}' adlı personel başarıyla eklendi.", 'success')
        return redirect(url_for('manage_personnel', calisan_id=new_id))
    potential_managers = get_db().execute('SELECT id, ad_soyad FROM calisanlar ORDER BY ad_soyad').fetchall()
    return render_template('add_personnel.html', managers=potential_managers)

@app.route('/personnel/manage/<int:calisan_id>')
@login_required
def manage_personnel(calisan_id):
    db = get_db()
    calisan = db.execute('SELECT * FROM calisanlar WHERE id = ?', (calisan_id,)).fetchone()
    if not calisan:
        return "Personel bulunamadı", 404
    evraklar = db.execute('SELECT * FROM evraklar WHERE calisan_id = ?', (calisan_id,)).fetchall()
    potential_managers = db.execute('SELECT id, ad_soyad, sicil_no FROM calisanlar WHERE id != ? ORDER BY ad_soyad', (calisan_id,)).fetchall()
    return render_template('personnel_manage.html', calisan=calisan, evraklar=evraklar, managers=potential_managers)

@app.route('/personnel/update/<int:calisan_id>', methods=['POST'])
@login_required
def update_personnel(calisan_id):
    db = get_db()
    form = request.form
    yonetici_id = form.get('yonetici_id') if form.get('yonetici_id') else None
    db.execute(
        "UPDATE calisanlar SET ad_soyad=?, ise_baslama_tarihi=?, sicil_no=?, sube=?, gorevi=?, tel=?, yakin_tel=?, tc_kimlik=?, adres=?, iban=?, egitim=?, ucreti=?, aciklama=?, yaka_tipi=?, isten_cikis_tarihi=?, yonetici_id=? WHERE id = ?",
        (form['ad_soyad'], form['ise_baslama_tarihi'], form['sicil_no'], form['sube'], form['gorevi'], form['tel'], form['yakin_tel'], form['tc_kimlik'], form['adres'], form['iban'], form['egitim'], form['ucreti'], form['aciklama'], form['yaka_tipi'], form['isten_cikis_tarihi'], yonetici_id, calisan_id)
    )
    db.commit()
    flash('Personel bilgileri güncellendi.', 'info')
    return redirect(url_for('manage_personnel', calisan_id=calisan_id))

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
    db.execute('UPDATE evraklar SET dosya_yolu = ?, yuklendi_mi = 1 WHERE calisan_id = ? AND evrak_tipi = ?',
               (filename, calisan_id, evrak_tipi))
    db.commit()
    flash(f"'{evrak_tipi}' yüklendi.", 'success')
    return redirect(url_for('manage_personnel', calisan_id=calisan_id))

@app.route('/uploads/<filename>')
@login_required
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/personnel/delete/<int:calisan_id>', methods=['POST'])
@login_required
def delete_personnel(calisan_id):
    db = get_db()
    files = db.execute('SELECT dosya_yolu FROM evraklar WHERE calisan_id = ? AND dosya_yolu IS NOT NULL', (calisan_id,)).fetchall()
    for file in files:
        try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'], file['dosya_yolu']))
        except OSError: pass
    db.execute('DELETE FROM calisanlar WHERE id = ?', (calisan_id,))
    db.commit()
    flash('Personel silindi.', 'success')
    return redirect(url_for('personnel_list'))

@app.route('/users')
@login_required
@admin_required
def user_management():
    db = get_db()
    users = db.execute("SELECT k.id, k.username, k.role, c.ad_soyad FROM kullanicilar k LEFT JOIN calisanlar c ON k.calisan_id = c.id ORDER BY k.username").fetchall()
    unlinked_personnel = db.execute("SELECT * FROM calisanlar WHERE id NOT IN (SELECT calisan_id FROM kullanicilar WHERE calisan_id IS NOT NULL)").fetchall()
    return render_template('user_management.html', users=users, unlinked_personnel=unlinked_personnel)

@app.route('/users/add', methods=['POST'])
@login_required
@admin_required
def add_user():
    username = request.form.get('username')
    password = request.form.get('password')
    role = request.form.get('role', 'user')
    calisan_id = request.form.get('calisan_id')
    if not username or not password or not calisan_id:
        flash('Tüm alanlar zorunludur.', 'danger')
        return redirect(url_for('user_management'))
    db = get_db()
    if db.execute('SELECT id FROM kullanicilar WHERE username = ?', (username,)).fetchone():
        flash(f"'{username}' kullanıcı adı zaten alınmış.", 'danger')
        return redirect(url_for('user_management'))
    hashed_password = generate_password_hash(password)
    db.execute('INSERT INTO kullanicilar (username, password, role, calisan_id) VALUES (?, ?, ?, ?)',
               (username, hashed_password, role, calisan_id))
    db.commit()
    flash(f"'{username}' adlı kullanıcı başarıyla oluşturuldu.", 'success')
    return redirect(url_for('user_management'))

@app.route('/users/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    db = get_db()
    user = db.execute('SELECT * FROM kullanicilar WHERE id = ?', (user_id,)).fetchone()
    if not user:
        return "Kullanıcı bulunamadı", 404
    if request.method == 'POST':
        new_password = request.form.get('password')
        new_role = request.form.get('role')
        calisan_id = request.form.get('calisan_id') if request.form.get('calisan_id') else None
        if user_id == session.get('user_id') and (new_role != session.get('role') or str(calisan_id) != str(session.get('calisan_id', ''))):
            flash('Kendi yetkinizi veya personel bağlantınızı değiştiremezsiniz.', 'danger')
            return redirect(url_for('edit_user', user_id=user_id))
        update_fields = []
        params = []
        if new_password:
            update_fields.append("password = ?")
            params.append(generate_password_hash(new_password))
        update_fields.append("role = ?")
        params.append(new_role)
        update_fields.append("calisan_id = ?")
        params.append(calisan_id)
        params.append(user_id)
        query = f"UPDATE kullanicilar SET {', '.join(update_fields)} WHERE id = ?"
        db.execute(query, tuple(params))
        db.commit()
        flash(f"'{user['username']}' kullanıcısının bilgileri güncellendi.", 'success')
        return redirect(url_for('user_management'))
    current_personnel = None
    if user['calisan_id']:
        current_personnel = db.execute('SELECT * FROM calisanlar WHERE id = ?', (user['calisan_id'],)).fetchone()
    unlinked_personnel = db.execute("SELECT * FROM calisanlar WHERE id NOT IN (SELECT calisan_id FROM kullanicilar WHERE calisan_id IS NOT NULL)").fetchall()
    return render_template('edit_user.html', user=user, current_personnel=current_personnel, unlinked_personnel=unlinked_personnel)

@app.route('/users/delete/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    if user_id == session['user_id']:
        flash('Kendi hesabınızı silemezsiniz.', 'danger')
        return redirect(url_for('user_management'))
    db = get_db()
    db.execute('DELETE FROM kullanicilar WHERE id = ?', (user_id,))
    db.commit()
    flash('Kullanıcı başarıyla silindi.', 'success')
    return redirect(url_for('user_management'))

@app.route('/leave', methods=['GET', 'POST'])
@login_required
def leave_management():
    db = get_db()
    calisan_id = session.get('calisan_id')
    user_role = session.get('role')
    if not calisan_id and user_role not in ['admin', 'manager']:
        flash("Hesabınız bir personel profiline bağlı değil. Lütfen yöneticinizle iletişime geçin.", "danger")
        return redirect(url_for('dashboard'))
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
        db.execute(
            "INSERT INTO izin_talepleri (calisan_id, izin_tipi, baslangic_tarihi, bitis_tarihi, gun_sayisi, aciklama, talep_tarihi) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (calisan_id, leave_type, start_date_str, end_date_str, day_diff, aciklama, datetime.now().strftime('%Y-%m-%d'))
        )
        db.commit()
        flash("İzin talebiniz başarıyla alınmıştır.", "success")
        return redirect(url_for('leave_management'))
    pending_requests = []
    if user_role == 'admin':
        pending_requests = db.execute("SELECT it.*, c.ad_soyad FROM izin_talepleri it JOIN calisanlar c ON it.calisan_id = c.id WHERE it.durum = 'Beklemede' ORDER BY it.talep_tarihi DESC").fetchall()
    elif user_role == 'manager':
        pending_requests = db.execute("SELECT it.*, c.ad_soyad FROM izin_talepleri it JOIN calisanlar c ON it.calisan_id = c.id WHERE it.durum = 'Beklemede' AND c.yonetici_id = ? ORDER BY it.talep_tarihi DESC", (calisan_id,)).fetchall()
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
            db.execute("UPDATE calisanlar SET yillik_izin_bakiye = yillik_izin_bakiye + ? WHERE id = ?", 
                       (leave_request['gun_sayisi'], leave_request['calisan_id']))
        flash("İzin talebi reddedildi.", "info")
    db.commit()
    return redirect(url_for('leave_management'))

@app.route('/profile')
@login_required
def profile():
    db = get_db()
    calisan_id = session.get('calisan_id')
    if not calisan_id:
        flash("Hesabınız bir personel profiline bağlı değil.", "warning")
        return redirect(url_for('dashboard'))

    personnel_info = db.execute('SELECT * FROM calisanlar WHERE id = ?', (calisan_id,)).fetchone()
    my_requests = db.execute('SELECT * FROM izin_talepleri WHERE calisan_id = ? ORDER BY talep_tarihi DESC', (calisan_id,)).fetchall()

    my_team = []
    if session.get('role') in ['admin', 'manager']:
        my_team = db.execute('SELECT id, ad_soyad, gorevi FROM calisanlar WHERE yonetici_id = ?', (calisan_id,)).fetchall()

    return render_template('profile.html', personnel=personnel_info, my_requests=my_requests, my_team=my_team)

# YENİ: Performans Yönetimi Rotaları
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
            db.execute("INSERT INTO degerlendirme_donemleri (donem_adi, baslangic_tarihi, bitis_tarihi) VALUES (?, ?, ?)",
                       (donem_adi, baslangic_tarihi, bitis_tarihi))
            db.commit()
            flash(f"'{donem_adi}' adlı değerlendirme dönemi başarıyla oluşturuldu.", "success")
        return redirect(url_for('performance_management'))

    periods = db.execute("SELECT * FROM degerlendirme_donemleri ORDER BY baslangic_tarihi DESC").fetchall()
    return render_template('performance_management.html', periods=periods)

@app.route('/performance/period/<int:period_id>', methods=['GET', 'POST'])
@login_required
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
            db.execute("INSERT INTO personel_hedefleri (calisan_id, donem_id, hedef_aciklamasi, agirlik) VALUES (?, ?, ?, ?)",
                       (calisan_id, period_id, hedef_aciklamasi, agirlik))
            db.commit()
            flash("Yeni hedef başarıyla eklendi.", "success")
        return redirect(url_for('performance_period_detail', period_id=period_id))

    employees_to_manage = []
    if session.get('role') == 'admin':
        employees_to_manage = db.execute("SELECT id, ad_soyad, sicil_no FROM calisanlar WHERE isten_cikis_tarihi IS NULL OR isten_cikis_tarihi = '' ORDER BY ad_soyad").fetchall()
    elif session.get('role') == 'manager':
        employees_to_manage = db.execute("SELECT id, ad_soyad, sicil_no FROM calisanlar WHERE (isten_cikis_tarihi IS NULL OR isten_cikis_tarihi = '') AND yonetici_id = ? ORDER BY ad_soyad", (session.get('calisan_id'),)).fetchall()

    targets = db.execute("""
        SELECT ph.*, c.ad_soyad FROM personel_hedefleri ph
        JOIN calisanlar c ON ph.calisan_id = c.id
        WHERE ph.donem_id = ? ORDER BY c.ad_soyad
    """, (period_id,)).fetchall()

    return render_template('performance_period_detail.html', period=period, employees=employees_to_manage, targets=targets)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        db = get_db()
        user = db.execute('SELECT * FROM kullanicilar WHERE username = ?', (username,)).fetchone()
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            session['calisan_id'] = user['calisan_id']
            return redirect(url_for('dashboard'))
        else:
            flash("Geçersiz kullanıcı adı veya şifre!", "danger")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("Başarıyla çıkış yaptınız.", "info")
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)