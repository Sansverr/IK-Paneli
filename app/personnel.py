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

bp = Blueprint('personnel', __name__, url_prefix='/personnel')

# --- SABİT LİSTELER ---
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

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']

def _build_personnel_query_filter(search_query, yaka_tipi, durum):
    """Personel listesi için SADECE filtreleri (WHERE) oluşturan yardımcı fonksiyon."""
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
    """Personelleri filtreleyerek listeler. (Veritabanı sorgusu optimize edildi)"""
    db = g.db
    search_query = request.args.get('q')
    yaka_tipi = request.args.get('yaka_tipi')
    durum = request.args.get('durum', 'aktif')

    where_clause, params, active_filter = _build_personnel_query_filter(search_query, yaka_tipi, durum)

    # --- DEĞİŞİKLİK 1: VERİTABANI SORGUSU OPTİMİZASYONU ---
    # Alt sorgular (subqueries) yerine LEFT JOIN ve GROUP BY kullanarak daha performanslı bir sorgu oluşturuldu.
    # Bu, özellikle personel sayısı arttığında sayfanın daha hızlı yüklenmesini sağlar.
    query = f"""
        SELECT
            c.*,
            s.sube_adi,
            g.gorev_adi,
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
    """Filtrelenmiş personel listesini dışa aktarır."""
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

    return Response(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment;filename=personel_listesi.xlsx"}
    )

@bp.route('/add', methods=('GET', 'POST'))
@login_required
def add():
    db = g.db
    potential_managers = db.execute('SELECT id, ad, soyad FROM calisanlar WHERE onay_durumu="Onaylandı" ORDER BY ad, soyad').fetchall()
    subeler = db.execute('SELECT * FROM subeler ORDER BY sube_adi').fetchall()
    departmanlar = db.execute('SELECT * FROM departmanlar ORDER BY departman_adi').fetchall()
    gorevler = db.execute('SELECT * FROM gorevler ORDER BY gorev_adi').fetchall()

    if request.method == 'POST':
        tc_kimlik = request.form.get('tc_kimlik')
        sicil_no = request.form.get('sicil_no')
        error = None

        if not sicil_no: error = "Sicil Numarası alanı zorunludur."
        elif db.execute('SELECT id FROM calisanlar WHERE sicil_no = ?', (sicil_no,)).fetchone():
            error = f"Girilen Sicil Numarası ({sicil_no}) zaten başka bir personel tarafından kullanılmaktadır."
        elif not tc_kimlik: error = "T.C. Kimlik Numarası alanı zorunludur."
        elif db.execute('SELECT id FROM calisanlar WHERE tc_kimlik = ?', (tc_kimlik,)).fetchone():
            error = f"Girilen T.C. Kimlik Numarası ({tc_kimlik}) zaten başka bir personel tarafından kullanılmaktadır."

        if error is None:
            onay_durumu = 'Onaylandı' if session.get('role') == 'admin' else 'Onay Bekliyor'
            cursor = db.cursor()

            cursor.execute("""
                INSERT INTO calisanlar (ad, soyad, sicil_no, tc_kimlik, ise_baslama_tarihi, dogum_tarihi, cinsiyet, kan_grubu, 
                tel, yakin_tel, mail, adres, sube_id, departman_id, gorev_id, yonetici_id, yaka_tipi, ucreti, iban, egitim, onay_durumu) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (request.form.get('ad').strip().title(), request.form.get('soyad').strip().title(), sicil_no, tc_kimlik, request.form.get('ise_baslama_tarihi'), 
                 request.form.get('dogum_tarihi'), request.form.get('cinsiyet'), request.form.get('kan_grubu'),
                 request.form.get('tel'), request.form.get('yakin_tel'), request.form.get('mail'), request.form.get('adres'), 
                 request.form.get('sube_id'), request.form.get('departman_id'), request.form.get('gorev_id'), 
                 request.form.get('yonetici_id'), request.form.get('yaka_tipi'), request.form.get('ucreti'), 
                 request.form.get('iban'), request.form.get('egitim'), onay_durumu))
            new_id = cursor.lastrowid

            for evrak in GEREKLI_OZLUK_EVRAKLARI:
                cursor.execute('INSERT INTO evraklar (calisan_id, evrak_tipi, kategori) VALUES (?, ?, ?)', (new_id, evrak, 'Özlük'))
            for surec in GEREKLI_ISE_BASLANGIC_SURECLERI:
                cursor.execute('INSERT INTO evraklar (calisan_id, evrak_tipi, kategori) VALUES (?, ?, ?)', (new_id, surec, 'İşe Başlangıç'))

            db.commit()
            flash(f"Yeni personel kaydı '{onay_durumu}' durumuyla oluşturuldu.", 'success')
            return redirect(url_for('personnel.manage', calisan_id=new_id))
        flash(error, 'danger')
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
    yonetici_id = form.get('yonetici_id') if form.get('yonetici_id') else None

    db.execute("""
        UPDATE calisanlar SET ad=?, soyad=?, sicil_no=?, tc_kimlik=?, ise_baslama_tarihi=?, dogum_tarihi=?, 
        cinsiyet=?, kan_grubu=?, tel=?, yakin_tel=?, mail=?, adres=?, sube_id=?, departman_id=?, gorev_id=?, 
        yonetici_id=?, yaka_tipi=?, ucreti=?, iban=?, egitim=?, aciklama=?, isten_cikis_tarihi=? 
        WHERE id = ?""",
        (form.get('ad').strip().title(), form.get('soyad').strip().title(), form.get('sicil_no'), form.get('tc_kimlik'), form.get('ise_baslama_tarihi'), 
         form.get('dogum_tarihi'), form.get('cinsiyet'), form.get('kan_grubu'), form.get('tel'), form.get('yakin_tel'),
         form.get('mail'), form.get('adres'), form.get('sube_id'), form.get('departman_id'), 
         form.get('gorev_id'), yonetici_id, form.get('yaka_tipi'), form.get('ucreti'), 
         form.get('iban'), form.get('egitim'), form.get('aciklama'), form.get('isten_cikis_tarihi'), 
         calisan_id))
    db.commit()
    flash('Personel bilgileri başarıyla güncellendi.', 'success')
    return redirect(url_for('personnel.manage', calisan_id=calisan_id))

@bp.route('/delete/<int:calisan_id>', methods=('POST',))
@admin_required
def delete(calisan_id):
    # --- DEĞİŞİKLİK 3: DOSYA SİLME MİMARİSİ GÜNCELLEMESİ ---
    # Personel silindiğinde, artık o personele ait olan tüm klasörü ve içindeki dosyaları siler.
    # Bu, dosya sisteminin daha temiz kalmasını sağlar.
    personnel_upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], str(calisan_id))
    if os.path.exists(personnel_upload_path):
        try:
            shutil.rmtree(personnel_upload_path)
        except OSError as e:
            flash(f"Personel dosyaları silinirken bir hata oluştu: {e}", "danger")
            # Hata oluşsa bile veritabanı kaydını silmeye devam et

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
        # --- DEĞİŞİKLİK 2: DOSYA YÜKLEME MİMARİSİ GÜNCELLEMESİ ---
        # Artık her personel için kendi ID'si ile bir alt klasör oluşturuluyor.
        # Örneğin, 5 ID'li personelin dosyaları "uploads/5/" klasörüne kaydedilir.
        # Bu, dosya sistemini daha düzenli ve yönetilebilir hale getirir.
        personnel_upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], str(calisan_id))
        os.makedirs(personnel_upload_path, exist_ok=True)

        safe_evrak_tipi = "".join(c for c in evrak['evrak_tipi'] if c.isalnum() or c in (' ', '_')).rstrip()
        filename = f"{safe_evrak_tipi.replace(' ', '_')}_{secure_filename(file.filename)}"

        # Dosya yolunu oluştur ve kaydet
        file.save(os.path.join(personnel_upload_path, filename))

        # Veritabanına göreli yolu (klasör dahil) kaydet
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
    # Bu fonksiyon, dosya yolu "5/dosya_adi.pdf" gibi olsa bile doğru çalışacaktır.
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