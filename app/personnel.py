from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for, current_app, send_from_directory, Response
)
from werkzeug.utils import secure_filename
from .auth import login_required, admin_required, personnel_linked_required
from .database import GEREKLI_EVRAKLAR 
import os
import sqlite3
import openpyxl
from io import BytesIO

bp = Blueprint('personnel', __name__, url_prefix='/personnel')

def allowed_file(filename):
    """Yüklenen dosyanın uzantısının izin verilenler listesinde olup olmadığını kontrol eder."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']

@bp.route('/')
@login_required
def list_personnel():
    """Personelleri filtreleyerek listeler."""
    search_query = request.args.get('q')
    yaka_tipi = request.args.get('yaka_tipi')
    durum = request.args.get('durum', 'aktif') 
    db = g.db

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

@bp.route('/add', methods=('GET', 'POST'))
@login_required
def add():
    """Yeni personel ekleme formunu gösterir ve personel ekleme işlemini yapar."""
    db = g.db
    potential_managers = db.execute('SELECT id, ad_soyad FROM calisanlar WHERE onay_durumu="Onaylandı" ORDER BY ad_soyad').fetchall()
    subeler = db.execute('SELECT * FROM subeler ORDER BY sube_adi').fetchall()
    gorevler = db.execute('SELECT * FROM gorevler ORDER BY gorev_adi').fetchall()

    if request.method == 'POST':
        tc_kimlik = request.form.get('tc_kimlik')
        sicil_no = request.form.get('sicil_no')
        error = None

        if not sicil_no:
            error = "Sicil Numarası alanı zorunludur."
        elif db.execute('SELECT id FROM calisanlar WHERE sicil_no = ?', (sicil_no,)).fetchone():
            error = f"Girilen Sicil Numarası ({sicil_no}) zaten başka bir personel tarafından kullanılmaktadır."
        elif not tc_kimlik:
            error = "T.C. Kimlik Numarası alanı zorunludur."
        elif db.execute('SELECT id FROM calisanlar WHERE tc_kimlik = ?', (tc_kimlik,)).fetchone():
            error = f"Girilen T.C. Kimlik Numarası ({tc_kimlik}) zaten başka bir personel tarafından kullanılmaktadır."

        if error is None:
            onay_durumu = 'Onaylandı' if session.get('role') == 'admin' else 'Onay Bekliyor'
            cursor = db.cursor()
            cursor.execute("INSERT INTO calisanlar (ad_soyad, ise_baslama_tarihi, sicil_no, tc_kimlik, mail, sube_id, gorev_id, tel, yakin_tel, adres, iban, egitim, ucreti, yaka_tipi, yonetici_id, onay_durumu) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (request.form.get('ad_soyad'), request.form.get('ise_baslama_tarihi'), sicil_no, tc_kimlik, request.form.get('mail'), request.form.get('sube_id'), request.form.get('gorev_id'), request.form.get('tel'), request.form.get('yakin_tel'), request.form.get('adres'), request.form.get('iban'), request.form.get('egitim'), request.form.get('ucreti'), request.form.get('yaka_tipi'), request.form.get('yonetici_id'), onay_durumu))
            new_id = cursor.lastrowid

            for evrak in GEREKLI_EVRAKLAR:
                cursor.execute('INSERT INTO evraklar (calisan_id, evrak_tipi) VALUES (?, ?)', (new_id, evrak))

            db.commit()

            flash(f"Yeni personel kaydı '{onay_durumu}' durumuyla oluşturuldu. Şimdi evrakları yükleyebilirsiniz.", 'success')
            return redirect(url_for('personnel.manage', calisan_id=new_id))

        flash(error, 'danger')

    return render_template('add_personnel.html', managers=potential_managers, subeler=subeler, gorevler=gorevler, form_data=request.form if request.method == 'POST' else {})


@bp.route('/manage/<int:calisan_id>')
@login_required
def manage(calisan_id):
    """Belirli bir personelin detaylarını ve yönetim sayfasını gösterir."""
    db = g.db
    calisan = db.execute("SELECT c.*, s.sube_adi, g.gorev_adi FROM calisanlar c LEFT JOIN subeler s ON c.sube_id = s.id LEFT JOIN gorevler g ON c.gorev_id = g.id WHERE c.id = ?", (calisan_id,)).fetchone()

    if not calisan:
        flash("Personel bulunamadı.", "danger")
        return redirect(url_for('personnel.list_personnel'))

    evraklar = db.execute('SELECT * FROM evraklar WHERE calisan_id = ?', (calisan_id,)).fetchall()
    potential_managers = db.execute('SELECT id, ad_soyad, sicil_no FROM calisanlar WHERE id != ? AND onay_durumu="Onaylandı" ORDER BY ad_soyad', (calisan_id,)).fetchall()
    subeler = db.execute('SELECT * FROM subeler ORDER BY sube_adi').fetchall()
    gorevler = db.execute('SELECT * FROM gorevler ORDER BY gorev_adi').fetchall()

    return render_template('personnel_manage.html', calisan=calisan, evraklar=evraklar, managers=potential_managers, subeler=subeler, gorevler=gorevler)

@bp.route('/update/<int:calisan_id>', methods=('POST',))
@admin_required
def update(calisan_id):
    """Personel bilgilerini günceller."""
    db = g.db
    form = request.form
    yonetici_id = form.get('yonetici_id') if form.get('yonetici_id') else None

    db.execute("UPDATE calisanlar SET ad_soyad=?, ise_baslama_tarihi=?, sicil_no=?, tc_kimlik=?, mail=?, sube_id=?, gorev_id=?, tel=?, yakin_tel=?, adres=?, iban=?, egitim=?, ucreti=?, aciklama=?, yaka_tipi=?, isten_cikis_tarihi=?, yonetici_id=? WHERE id = ?",
        (form.get('ad_soyad'), form.get('ise_baslama_tarihi'), form.get('sicil_no'), form.get('tc_kimlik'), form.get('mail'), form.get('sube_id'), form.get('gorev_id'), form.get('tel'), form.get('yakin_tel'), form.get('adres'), form.get('iban'), form.get('egitim'), form.get('ucreti'), form.get('aciklama'), form.get('yaka_tipi'), form.get('isten_cikis_tarihi'), yonetici_id, calisan_id))
    db.commit()
    flash('Personel bilgileri başarıyla güncellendi.', 'success')
    return redirect(url_for('personnel.manage', calisan_id=calisan_id))

@bp.route('/delete/<int:calisan_id>', methods=('POST',))
@admin_required
def delete(calisan_id):
    """Bir personeli ve ilişkili tüm verilerini siler."""
    db = g.db
    files = db.execute('SELECT dosya_yolu FROM evraklar WHERE calisan_id = ? AND dosya_yolu IS NOT NULL', (calisan_id,)).fetchall()
    for file in files:
        try:
            os.remove(os.path.join(current_app.config['UPLOAD_FOLDER'], file['dosya_yolu']))
        except OSError:
            pass 
    db.execute('DELETE FROM calisanlar WHERE id = ?', (calisan_id,))
    db.commit()
    flash('Personel ve ilişkili tüm verileri kalıcı olarak silindi.', 'success')
    return redirect(url_for('personnel.list_personnel'))

@bp.route('/upload/<int:calisan_id>/<string:evrak_tipi>', methods=['POST'])
@login_required
def upload_file_route(calisan_id, evrak_tipi):
    """Personel için evrak yükleme işlemini yapar."""
    if 'file' not in request.files:
        flash('Dosya seçilmedi.', 'danger')
        return redirect(request.url)

    file = request.files['file']
    if file.filename == '':
        flash('Dosya seçilmedi.', 'danger')
        return redirect(url_for('personnel.manage', calisan_id=calisan_id))

    if file and allowed_file(file.filename):
        filename = f"{calisan_id}_{evrak_tipi.replace(' ', '_')}_{secure_filename(file.filename)}"
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        db = g.db
        db.execute('UPDATE evraklar SET dosya_yolu = ?, yuklendi_mi = 1 WHERE calisan_id = ? AND evrak_tipi = ?',
                   (filename, calisan_id, evrak_tipi))
        db.commit()
        flash(f"'{evrak_tipi}' belgesi başarıyla yüklendi.", 'success')
    else:
        flash('İzin verilmeyen dosya türü.', 'danger')

    return redirect(url_for('personnel.manage', calisan_id=calisan_id))

@bp.route('/uploads/<path:filename>')
@login_required
def uploaded_file(filename):
    """Yüklenmiş dosyaları güvenli bir şekilde sunar."""
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)

# --- YENİ EKLENEN DECORATOR İLE DÜZELTİLMİŞ PROFİL FONKSİYONU ---
@bp.route('/profile')
@login_required
@personnel_linked_required
def profile():
    """Giriş yapmış kullanıcının profil sayfasını gösterir."""
    db = g.db
    calisan_id = session.get('calisan_id')

    personnel_info = db.execute(
        "SELECT c.*, s.sube_adi, g.gorev_adi FROM calisanlar c "
        "LEFT JOIN subeler s ON c.sube_id = s.id "
        "LEFT JOIN gorevler g ON c.gorev_id = g.id "
        "WHERE c.id = ?", (calisan_id,)
    ).fetchone()
    my_requests = db.execute('SELECT * FROM izin_talepleri WHERE calisan_id = ? ORDER BY talep_tarihi DESC', (calisan_id,)).fetchall()

    my_team = []
    if session.get('role') in ['admin', 'manager']:
        my_team = db.execute(
            "SELECT c.id, c.ad_soyad, g.gorev_adi FROM calisanlar c "
            "LEFT JOIN gorevler g ON c.gorev_id = g.id "
            "WHERE c.yonetici_id = ? AND c.onay_durumu = 'Onaylandı'", (calisan_id,)
        ).fetchall()

    return render_template('profile.html', personnel=personnel_info, my_requests=my_requests, my_team=my_team)

@bp.route('/export/<string:file_type>')
@login_required
def export(file_type):
    """Filtrelenmiş personel listesini dışa aktarır."""
    db = g.db

    search_query = request.args.get('q')
    yaka_tipi = request.args.get('yaka_tipi')
    durum = request.args.get('durum', 'aktif') 

    base_query = "SELECT c.ad_soyad, c.sicil_no, c.tc_kimlik, c.ise_baslama_tarihi, s.sube_adi, g.gorev_adi, c.yaka_tipi FROM calisanlar c LEFT JOIN subeler s ON c.sube_id = s.id LEFT JOIN gorevler g ON c.gorev_id = g.id"
    conditions = ["c.onay_durumu = 'Onaylandı'"] 
    params = []

    if search_query:
        conditions.append("(c.ad_soyad LIKE ? OR c.sicil_no LIKE ?)")
        params.extend([f'%{search_query}%', f'%{search_query}%'])
    if yaka_tipi:
        conditions.append("c.yaka_tipi = ?")
        params.append(yaka_tipi)
    if durum == 'ayrilan':
        conditions.append("c.isten_cikis_tarihi IS NOT NULL AND c.isten_cikis_tarihi != ''")
    else: 
        conditions.append("(c.isten_cikis_tarihi IS NULL OR c.isten_cikis_tarihi = '')")

    base_query += " WHERE " + " AND ".join(conditions)
    calisanlar = db.execute(base_query, params).fetchall()

    if file_type == 'excel':
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "Personel Listesi"

        headers = ["Adı Soyadı", "Sicil No", "TC Kimlik", "İşe Başlama", "Şube", "Görev", "Yaka Tipi"]
        sheet.append(headers)

        for calisan in calisanlar:
            sheet.append(list(calisan))

        output = BytesIO()
        workbook.save(output)
        output.seek(0)

        return Response(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment;filename=personel_listesi.xlsx"}
        )

    flash("Sadece Excel formatında dışa aktarma desteklenmektedir.", "info")
    return redirect(url_for('personnel.list_personnel'))