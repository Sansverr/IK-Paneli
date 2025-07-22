# app/personnel.py

from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for, current_app, send_from_directory, Response
)
from werkzeug.utils import secure_filename
from .auth import login_required, admin_required, personnel_linked_required
import os
import shutil
import sqlite3
import openpyxl
from io import BytesIO
from datetime import datetime, date

bp = Blueprint('personnel', __name__, url_prefix='/personnel')

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']

def _build_personnel_query_filter(search_query, yaka_tipi, durum):
    conditions = ["c.onay_durumu = 'Onaylandı'"]
    params = []
    active_filter_text = ""
    if search_query:
        conditions.append("(c.ad || ' ' || c.soyad LIKE ? OR c.sicil_no LIKE ?)")
        params.extend([f'%{search_query}%', f'%{search_query}%'])
    if yaka_tipi:
        conditions.append("c.yaka_tipi = ?")
        params.append(yaka_tipi)
    if durum == 'ayrilan':
        conditions.append("c.isten_cikis_tarihi IS NOT NULL AND c.isten_cikis_tarihi != ''")
        active_filter_text = "Ayrılan Personeller"
    else:
        conditions.append("(c.isten_cikis_tarihi IS NULL OR c.isten_cikis_tarihi = '')")
        active_filter_text = "Aktif Çalışanlar"
    if yaka_tipi:
        active_filter_text = yaka_tipi.replace("_", " ").title()
    where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
    return where_clause, params, active_filter_text

@bp.route('/')
@login_required
def list_personnel():
    db = g.db
    search_query = request.args.get('q')
    yaka_tipi = request.args.get('yaka_tipi')
    durum = request.args.get('durum', 'aktif')
    where_clause, params, active_filter = _build_personnel_query_filter(search_query, yaka_tipi, durum)
    query = f"""
        SELECT
            c.*, s.sube_adi, g.gorev_adi,
            SUM(CASE WHEN e.kategori = 'Özlük' AND e.yuklendi_mi = 1 THEN 1 ELSE 0 END) as yuklenen_evrak,
            SUM(CASE WHEN e.kategori = 'Özlük' THEN 1 ELSE 0 END) as toplam_evrak
        FROM calisanlar c
        LEFT JOIN subeler s ON c.sube_id = s.id
        LEFT JOIN gorevler g ON c.gorev_id = g.id
        LEFT JOIN evraklar e ON c.id = e.calisan_id
        {where_clause}
        GROUP BY c.id
        ORDER BY c.ad, c.soyad
    """
    calisanlar = db.execute(query, params).fetchall()
    return render_template('personnel_list.html', calisanlar=calisanlar, active_filter=active_filter)

@bp.route('/export/<string:file_type>')
@login_required
def export(file_type):
    if file_type != 'excel':
        flash("Sadece Excel formatında dışa aktarma desteklenmektedir.", "info")
        return redirect(url_for('personnel.list_personnel'))
    db = g.db
    search_query = request.args.get('q')
    yaka_tipi = request.args.get('yaka_tipi')
    durum = request.args.get('durum', 'aktif')
    where_clause, params, _ = _build_personnel_query_filter(search_query, yaka_tipi, durum)
    query = f"""
        SELECT c.ad, c.soyad, c.sicil_no, c.tc_kimlik, c.ise_baslama_tarihi, s.sube_adi, d.departman_adi, g.gorev_adi, c.yaka_tipi
        FROM calisanlar c
        LEFT JOIN subeler s ON c.sube_id = s.id
        LEFT JOIN departmanlar d ON c.departman_id = d.id
        LEFT JOIN gorevler g ON c.gorev_id = g.id
        {where_clause}
        ORDER BY c.ad, c.soyad
    """
    calisanlar = db.execute(query, params).fetchall()
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Personel Listesi"
    headers = ["Ad", "Soyad", "Sicil No", "TC Kimlik", "İşe Başlama", "Şube", "Departman", "Görev", "Yaka Tipi"]
    sheet.append(headers)
    for calisan in calisanlar:
        sheet.append([str(col) if col is not None else '' for col in calisan])
    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return Response(output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": "attachment;filename=personel_listesi.xlsx"})

@bp.route('/add', methods=('GET', 'POST'))
@login_required
@admin_required
def add():
    db = g.db
    potential_managers = db.execute('SELECT id, ad, soyad FROM calisanlar WHERE onay_durumu="Onaylandı" ORDER BY ad, soyad').fetchall()
    subeler = db.execute('SELECT * FROM subeler ORDER BY sube_adi').fetchall()
    departmanlar = db.execute('SELECT * FROM departmanlar ORDER BY departman_adi').fetchall()
    gorevler = db.execute('SELECT * FROM gorevler ORDER BY gorev_adi').fetchall()
    if request.method == 'POST':
        form_data = request.form
        error = None
        required_fields = [
            'ad', 'soyad', 'tc_kimlik', 'dogum_tarihi', 'cinsiyet', 'kan_grubu',
            'mail', 'tel', 'yakin_tel', 'adres', 'sicil_no', 'ise_baslama_tarihi',
            'sube_id', 'departman_id', 'gorev_id', 'yaka_tipi', 'egitim'
        ]
        if any(not form_data.get(field) for field in required_fields):
            error = "Lütfen IBAN ve Ücreti dışındaki tüm zorunlu alanları doldurun."
        if not error:
            tel = form_data.get('tel', '')
            if not tel.isdigit() or len(tel) != 11:
                error = "Telefon numarası 11 haneli bir sayı olmalıdır."
        if not error:
            tc_kimlik = form_data.get('tc_kimlik')
            if not tc_kimlik.isdigit() or len(tc_kimlik) != 11:
                error = "T.C. Kimlik Numarası 11 haneli bir sayı olmalıdır."
            elif db.execute('SELECT id FROM calisanlar WHERE tc_kimlik = ?', (tc_kimlik,)).fetchone():
                error = f"Girilen T.C. Kimlik Numarası ({tc_kimlik}) zaten başka bir personel tarafından kullanılmaktadır."
        if not error:
            mail = form_data.get('mail')
            if db.execute('SELECT id FROM calisanlar WHERE mail = ?', (mail,)).fetchone():
                error = f"Girilen e-posta adresi ({mail}) zaten başka bir personel tarafından kullanılmaktadır."
        if not error:
            sicil_no = form_data.get('sicil_no')
            if db.execute('SELECT id FROM calisanlar WHERE sicil_no = ?', (sicil_no,)).fetchone():
                error = f"Girilen Sicil Numarası ({sicil_no}) zaten başka bir personel tarafından kullanılmaktadır."
        age = None
        if not error:
            try:
                birth_date_str = form_data.get('dogum_tarihi')
                birth_date = datetime.strptime(birth_date_str, '%Y-%m-%d').date()
                today = date.today()
                age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
                if age < 16:
                    error = "Personel 16 yaşından küçük olamaz."
            except (ValueError, TypeError):
                error = "Geçersiz doğum tarihi formatı."
        if error:
            flash(error, 'danger')
        else:
            onay_durumu = 'Onaylandı' if session.get('role') == 'admin' else 'Onay Bekliyor'
            cursor = db.cursor()
            cursor.execute("""
                INSERT INTO calisanlar (ad, soyad, sicil_no, tc_kimlik, ise_baslama_tarihi, dogum_tarihi, cinsiyet, kan_grubu,
                tel, yakin_tel, mail, adres, sube_id, departman_id, gorev_id, yonetici_id, yaka_tipi, ucreti, iban, egitim, onay_durumu)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (form_data.get('ad').strip().title(), form_data.get('soyad').strip().title(), form_data.get('sicil_no'), form_data.get('tc_kimlik'), form_data.get('ise_baslama_tarihi'),
                 form_data.get('dogum_tarihi'), form_data.get('cinsiyet'), form_data.get('kan_grubu'), form_data.get('tel'), form_data.get('yakin_tel'),
                 form_data.get('mail'), form_data.get('adres'), form_data.get('sube_id'), form_data.get('departman_id'), form_data.get('gorev_id'),
                 form_data.get('yonetici_id'), form_data.get('yaka_tipi'), form_data.get('ucreti'), form_data.get('iban'),
                 form_data.get('egitim'), onay_durumu))
            new_id = cursor.lastrowid
            gerekli_evraklar = db.execute("SELECT evrak_adi, kategori FROM evrak_tipleri").fetchall()
            for evrak in gerekli_evraklar:
                cursor.execute('INSERT INTO evraklar (calisan_id, evrak_tipi, kategori) VALUES (?, ?, ?)',
                               (new_id, evrak['evrak_adi'], evrak['kategori']))
            db.commit()
            flash("Yeni personel kaydı başarıyla oluşturuldu.", 'success')
            if age is not None and 16 <= age < 18:
                flash("Uyarı: Eklenen personel 18 yaşından küçüktür.", "warning")
            return redirect(url_for('personnel.manage', calisan_id=new_id))
    return render_template('add_personnel.html', managers=potential_managers, subeler=subeler, departmanlar=departmanlar, gorevler=gorevler, form_data=request.form if request.method == 'POST' else {})

@bp.route('/manage/<int:calisan_id>')
@login_required
def manage(calisan_id):
    db = g.db
    calisan = db.execute("""
        SELECT c.*, s.sube_adi, d.departman_adi, g.gorev_adi
        FROM calisanlar c
        LEFT JOIN subeler s ON c.sube_id = s.id
        LEFT JOIN departmanlar d ON c.departman_id = d.id
        LEFT JOIN gorevler g ON c.gorev_id = g.id
        WHERE c.id = ?""", (calisan_id,)).fetchone()
    if not calisan:
        flash("Personel bulunamadı.", "danger")
        return redirect(url_for('personnel.list_personnel'))
    ozluk_evraklari = db.execute("SELECT * FROM evraklar WHERE calisan_id = ? AND kategori = 'Özlük' ORDER BY id", (calisan_id,)).fetchall()
    ise_baslangic_surecleri = db.execute("SELECT * FROM evraklar WHERE calisan_id = ? AND kategori = 'İşe Başlangıç' ORDER BY id", (calisan_id,)).fetchall()
    potential_managers = db.execute('SELECT id, ad, soyad, sicil_no FROM calisanlar WHERE id != ? AND onay_durumu="Onaylandı" ORDER BY ad, soyad', (calisan_id,)).fetchall()
    subeler = db.execute('SELECT * FROM subeler ORDER BY sube_adi').fetchall()
    departmanlar = db.execute('SELECT * FROM departmanlar ORDER BY departman_adi').fetchall()
    gorevler = db.execute('SELECT * FROM gorevler ORDER BY gorev_adi').fetchall()
    return render_template(
        'personnel_manage.html',
        calisan=calisan,
        ozluk_evraklari=ozluk_evraklari,
        ise_baslangic_surecleri=ise_baslangic_surecleri,
        managers=potential_managers,
        subeler=subeler,
        departmanlar=departmanlar,
        gorevler=gorevler
    )

@bp.route('/update/<int:calisan_id>', methods=('POST',))
@admin_required
def update(calisan_id):
    db = g.db
    form = request.form
    error = None

    # Sadece düzenlenebilir alanlar için doğrulama yapılır
    editable_fields = [
        'mail', 'tel', 'yakin_tel', 'adres', 'sube_id', 'departman_id', 'gorev_id',
        'yaka_tipi', 'egitim', 'ucreti', 'iban', 'yonetici_id', 'isten_cikis_tarihi', 'aciklama'
    ]

    # Telefon format kontrolü
    tel = form.get('tel', '')
    if not tel.isdigit() or len(tel) != 11:
        error = "Telefon numarası 11 haneli bir sayı olmalıdır."

    # E-posta benzersizlik kontrolü
    if not error:
        mail = form.get('mail')
        if not mail:
            error = "E-posta adresi boş bırakılamaz."
        else:
            existing_mail = db.execute('SELECT id FROM calisanlar WHERE mail = ? AND id != ?', (mail, calisan_id)).fetchone()
            if existing_mail:
                error = f"Girilen e-posta adresi ({mail}) zaten başka bir personele aittir."

    if error:
        flash(error, 'danger')
        return redirect(url_for('personnel.manage', calisan_id=calisan_id))

    # Sadece düzenlenebilir alanları içeren bir güncelleme sorgusu oluştur
    update_query = "UPDATE calisanlar SET "
    update_params = []
    update_fields = []

    for field in editable_fields:
        if field in form:
            update_fields.append(f"{field} = ?")
            value = form.get(field)
            # Yönetici ID'si boş olabilir
            if field == 'yonetici_id' and not value:
                update_params.append(None)
            else:
                update_params.append(value)

    if update_fields:
        update_query += ", ".join(update_fields)
        update_query += " WHERE id = ?"
        update_params.append(calisan_id)

        db.execute(update_query, tuple(update_params))
        db.commit()
        flash('Personel bilgileri başarıyla güncellendi.', 'success')

    return redirect(url_for('personnel.manage', calisan_id=calisan_id))

@bp.route('/delete/<int:calisan_id>', methods=('POST',))
@admin_required
def delete(calisan_id):
    personnel_upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], str(calisan_id))
    if os.path.exists(personnel_upload_path):
        try:
            shutil.rmtree(personnel_upload_path)
        except OSError as e:
            flash(f"Personel dosyaları silinirken bir hata oluştu: {e}", "danger")
    db = g.db
    db.execute('DELETE FROM calisanlar WHERE id = ?', (calisan_id,))
    db.commit()
    flash('Personel ve ilişkili tüm verileri (dosyalar dahil) kalıcı olarak silindi.', 'success')
    return redirect(url_for('personnel.list_personnel'))

@bp.route('/upload/<int:calisan_id>/<int:evrak_id>', methods=['POST'])
@login_required
def upload_file_route(calisan_id, evrak_id):
    if 'file' not in request.files:
        flash('Dosya seçilmedi.', 'danger')
        return redirect(url_for('personnel.manage', calisan_id=calisan_id))
    file = request.files['file']
    if file.filename == '':
        flash('Dosya seçilmedi.', 'danger')
        return redirect(url_for('personnel.manage', calisan_id=calisan_id))
    db = g.db
    evrak = db.execute("SELECT evrak_tipi FROM evraklar WHERE id = ?", (evrak_id,)).fetchone()
    if not evrak:
        flash("Geçersiz evrak ID'si.", "danger")
        return redirect(url_for('personnel.manage', calisan_id=calisan_id))
    if file and allowed_file(file.filename):
        personnel_upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], str(calisan_id))
        os.makedirs(personnel_upload_path, exist_ok=True)
        safe_evrak_tipi = "".join(c for c in evrak['evrak_tipi'] if c.isalnum() or c in (' ', '_')).rstrip()
        filename = f"{safe_evrak_tipi.replace(' ', '_')}_{secure_filename(file.filename)}"
        file.save(os.path.join(personnel_upload_path, filename))
        db_path = os.path.join(str(calisan_id), filename)
        db.execute('UPDATE evraklar SET dosya_yolu = ?, yuklendi_mi = 1 WHERE id = ?', (db_path, evrak_id))
        db.commit()
        flash(f"'{evrak['evrak_tipi']}' belgesi başarıyla yüklendi.", 'success')
    else:
        flash('İzin verilmeyen dosya türü.', 'danger')
    return redirect(url_for('personnel.manage', calisan_id=calisan_id))

@bp.route('/uploads/<path:filename>')
@login_required
def uploaded_file(filename):
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)

@bp.route('/note/update/<int:evrak_id>', methods=['POST'])
@admin_required
def update_note(evrak_id):
    note_content = request.form.get('notlar')
    db = g.db
    evrak = db.execute("SELECT calisan_id FROM evraklar WHERE id = ?", (evrak_id,)).fetchone()
    if not evrak:
        flash("İşlem yapılacak madde bulunamadı.", "danger")
        return redirect(url_for('personnel.list_personnel'))
    db.execute("UPDATE evraklar SET notlar = ? WHERE id = ?", (note_content, evrak_id))
    db.commit()
    flash("Zimmet notu başarıyla güncellendi.", "success")
    return redirect(url_for('personnel.manage', calisan_id=evrak['calisan_id']))

@bp.route('/profile')
@login_required
@personnel_linked_required
def profile():
    db = g.db
    calisan_id = session.get('calisan_id')
    personnel_info = db.execute(
        """SELECT c.*, s.sube_adi, d.departman_adi, g.gorev_adi
           FROM calisanlar c
           LEFT JOIN subeler s ON c.sube_id = s.id
           LEFT JOIN departmanlar d ON c.departman_id = d.id
           LEFT JOIN gorevler g ON c.gorev_id = g.id
           WHERE c.id = ?""", (calisan_id,)
    ).fetchone()
    my_requests = db.execute('SELECT * FROM izin_talepleri WHERE calisan_id = ? ORDER BY talep_tarihi DESC', (calisan_id,)).fetchall()
    my_team = []
    if session.get('role') in ['admin', 'manager']:
        my_team = db.execute(
            """SELECT c.id, c.ad, c.soyad, g.gorev_adi
               FROM calisanlar c
               LEFT JOIN gorevler g ON c.gorev_id = g.id
               WHERE c.yonetici_id = ? AND c.onay_durumu = 'Onaylandı'""", (calisan_id,)
        ).fetchall()
    return render_template('profile.html', personnel=personnel_info, my_requests=my_requests, my_team=my_team)