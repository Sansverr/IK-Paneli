# app/personnel.py

import os
import shutil
from flask import (
    Blueprint, flash, redirect, render_template, request, url_for, current_app, send_from_directory, Response
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from datetime import datetime, date
from io import BytesIO
import openpyxl
from sqlalchemy import or_, and_, func
from types import SimpleNamespace

# Yeni SQLAlchemy yapısı için gerekli importlar
from .database import db, Personnel, User, Evrak, Sube, Departman, Gorev, EvrakTipi
from .auth import admin_required, personnel_linked_required

bp = Blueprint('personnel', __name__, url_prefix='/personnel')

def allowed_file(filename):
    """İzin verilen dosya uzantılarını config dosyasından kontrol eder."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']

# --- Personel Listeleme ve Dışa Aktarma ---

@bp.route('/')
@login_required
def list_personnel():
    """Filtrelenmiş personel listesini gösterir."""
    search_query = request.args.get('q')
    yaka_tipi = request.args.get('yaka_tipi')
    durum = request.args.get('durum', 'aktif')

    # Yüklenen ve toplam evrak sayılarını hesaplamak için alt sorgular
    yuklenen_evrak_subquery = db.session.query(func.count(Evrak.id)).filter(
        Evrak.calisan_id == Personnel.id, 
        Evrak.kategori == 'Özlük',
        Evrak.yuklendi_mi == True
    ).correlate(Personnel).as_scalar()

    toplam_evrak_subquery = db.session.query(func.count(Evrak.id)).filter(
        Evrak.calisan_id == Personnel.id,
        Evrak.kategori == 'Özlük'
    ).correlate(Personnel).as_scalar()

    query = db.session.query(
        Personnel, Sube.sube_adi, Gorev.gorev_adi,
        yuklenen_evrak_subquery.label('yuklenen_evrak'),
        toplam_evrak_subquery.label('toplam_evrak')
    ).outerjoin(Sube, Personnel.sube_id == Sube.id)\
     .outerjoin(Gorev, Personnel.gorev_id == Gorev.id)

    active_filter = "Aktif Çalışanlar"
    query = query.filter(Personnel.onay_durumu == 'Onaylandı')

    if search_query:
        search_term = f"%{search_query}%"
        query = query.filter(or_((Personnel.ad + " " + Personnel.soyad).like(search_term), Personnel.sicil_no.like(search_term)))
    if yaka_tipi:
        query = query.filter(Personnel.yaka_tipi == yaka_tipi)
        active_filter = yaka_tipi.replace("_", " ").title()
    if durum == 'ayrilan':
        query = query.filter(Personnel.isten_cikis_tarihi != None)
        active_filter = "Ayrılan Personeller"
    else:
        query = query.filter(Personnel.isten_cikis_tarihi == None)

    try:
        results = query.order_by(Personnel.ad, Personnel.soyad).all()

        # --- NİHAİ DÜZELTME: Veriyi HTML şablonu için uyumlu hale getir ---
        # SQLAlchemy'nin karmaşık sonuç yapısını, şablonun beklediği basit yapıya dönüştürür.
        # Bu, '... object has no attribute 'id'' hatasını çözer.
        personnel_list_for_template = []
        for row in results:
            # Personnel nesnesinin tüm özelliklerini kopyala
            calisan = SimpleNamespace(**row.Personnel.__dict__)
            # Sorgudan gelen ek verileri ekle
            calisan.sube_adi = row.sube_adi
            calisan.gorev_adi = row.gorev_adi
            calisan.yuklenen_evrak = row.yuklenen_evrak or 0
            calisan.toplam_evrak = row.toplam_evrak or 0
            personnel_list_for_template.append(calisan)

    except Exception as e:
        flash(f"Personel listesi yüklenirken bir hata oluştu: {e}", "danger")
        personnel_list_for_template = []

    return render_template('personnel_list.html', calisanlar=personnel_list_for_template, active_filter=active_filter)

@bp.route('/export/<string:file_type>')
@login_required
def export(file_type):
    """Filtrelenmiş personel listesini Excel olarak dışa aktarır."""
    if file_type != 'excel':
        flash("Sadece Excel formatı desteklenmektedir.", "warning")
        return redirect(url_for('personnel.list_personnel'))
    try:
        search_query = request.args.get('q')
        yaka_tipi = request.args.get('yaka_tipi')
        durum = request.args.get('durum', 'aktif')

        query = db.session.query(
            Personnel.ad, Personnel.soyad, Personnel.sicil_no, Personnel.tc_kimlik, Personnel.ise_baslama_tarihi,
            Sube.sube_adi, Departman.departman_adi, Gorev.gorev_adi, Personnel.yaka_tipi
        ).outerjoin(Sube, Personnel.sube_id == Sube.id)\
         .outerjoin(Departman, Personnel.departman_id == Departman.id)\
         .outerjoin(Gorev, Personnel.gorev_id == Gorev.id)\
         .filter(Personnel.onay_durumu == 'Onaylandı')

        if search_query:
            search_term = f"%{search_query}%"
            query = query.filter(or_((Personnel.ad + " " + Personnel.soyad).like(search_term), Personnel.sicil_no.like(search_term)))
        if yaka_tipi:
            query = query.filter(Personnel.yaka_tipi == yaka_tipi)
        if durum == 'ayrilan':
            query = query.filter(Personnel.isten_cikis_tarihi != None)
        else:
            query = query.filter(Personnel.isten_cikis_tarihi == None)

        personnel_data = query.order_by(Personnel.ad, Personnel.soyad).all()

        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "Personel Listesi"
        headers = ["Ad", "Soyad", "Sicil No", "TC Kimlik", "İşe Başlama", "Şube", "Departman", "Görev", "Yaka Tipi"]
        sheet.append(headers)

        for p_row in personnel_data:
            sheet.append([str(col) if col is not None else '' for col in p_row])

        output = BytesIO()
        workbook.save(output)
        output.seek(0)

        return Response(output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 
                        headers={"Content-Disposition": "attachment;filename=personel_listesi.xlsx"})
    except Exception as e:
        flash(f"Excel dosyası oluşturulurken bir hata oluştu: {e}", "danger")
        return redirect(url_for('personnel.list_personnel'))

@bp.route('/add', methods=('GET', 'POST'))
@admin_required
def add():
    if request.method == 'POST':
        form = request.form
        error = None
        if Personnel.query.filter_by(tc_kimlik=form.get('tc_kimlik')).first():
            error = "Bu T.C. Kimlik Numarası zaten kayıtlı."
        elif Personnel.query.filter_by(mail=form.get('mail')).first():
            error = "Bu e-posta adresi zaten kayıtlı."
        elif form.get('sicil_no') and Personnel.query.filter_by(sicil_no=form.get('sicil_no')).first():
            error = "Bu sicil numarası zaten kayıtlı."

        if error:
            flash(error, 'danger')
        else:
            try:
                onay_durumu = 'Onaylandı' if current_user.role == 'admin' else 'Onay Bekliyor'
                new_personnel = Personnel(
                    ad=form.get('ad').strip().title(), soyad=form.get('soyad').strip().title(),
                    sicil_no=form.get('sicil_no'), tc_kimlik=form.get('tc_kimlik'),
                    ise_baslama_tarihi=datetime.strptime(form.get('ise_baslama_tarihi'), '%Y-%m-%d').date() if form.get('ise_baslama_tarihi') else None,
                    dogum_tarihi=datetime.strptime(form.get('dogum_tarihi'), '%Y-%m-%d').date() if form.get('dogum_tarihi') else None,
                    cinsiyet=form.get('cinsiyet'), kan_grubu=form.get('kan_grubu'),
                    tel=form.get('tel'), yakin_tel=form.get('yakin_tel'), mail=form.get('mail'),
                    adres=form.get('adres'), sube_id=form.get('sube_id'), departman_id=form.get('departman_id'),
                    gorev_id=form.get('gorev_id'), yonetici_id=form.get('yonetici_id') if form.get('yonetici_id') else None,
                    yaka_tipi=form.get('yaka_tipi'), ucreti=form.get('ucreti'), iban=form.get('iban'),
                    egitim=form.get('egitim'), onay_durumu=onay_durumu
                )
                db.session.add(new_personnel)
                db.session.flush()

                gerekli_evraklar = EvrakTipi.query.all()
                for evrak_tipi in gerekli_evraklar:
                    yeni_evrak = Evrak(calisan_id=new_personnel.id, evrak_tipi=evrak_tipi.evrak_adi, kategori=evrak_tipi.kategori)
                    db.session.add(yeni_evrak)

                db.session.commit()
                flash("Yeni personel kaydı başarıyla oluşturuldu.", 'success')
                return redirect(url_for('personnel.manage', calisan_id=new_personnel.id))
            except Exception as e:
                db.session.rollback()
                flash(f"Personel eklenirken bir hata oluştu: {e}", 'danger')

    potential_managers = Personnel.query.filter_by(onay_durumu="Onaylandı").order_by(Personnel.ad, Personnel.soyad).all()
    subeler = Sube.query.order_by(Sube.sube_adi).all()
    departmanlar = Departman.query.order_by(Departman.departman_adi).all()
    gorevler = Gorev.query.order_by(Gorev.gorev_adi).all()
    return render_template('add_personnel.html', managers=potential_managers, subeler=subeler, departmanlar=departmanlar, gorevler=gorevler, form_data=request.form if request.method == 'POST' else {})

@bp.route('/manage/<int:calisan_id>')
@login_required
def manage(calisan_id):
    personnel = Personnel.query.get_or_404(calisan_id)
    ozluk_evraklari = Evrak.query.filter_by(calisan_id=calisan_id, kategori='Özlük').order_by(Evrak.id).all()
    ise_baslangic_surecleri = Evrak.query.filter_by(calisan_id=calisan_id, kategori='İşe Başlangıç').order_by(Evrak.id).all()

    potential_managers = Personnel.query.filter(Personnel.id != calisan_id, Personnel.onay_durumu=="Onaylandı").order_by(Personnel.ad, Personnel.soyad).all()
    subeler = Sube.query.order_by(Sube.sube_adi).all()
    departmanlar = Departman.query.order_by(Departman.departman_adi).all()
    gorevler = Gorev.query.order_by(Gorev.gorev_adi).all()

    return render_template('personnel_manage.html', calisan=personnel, ozluk_evraklari=ozluk_evraklari,
                           ise_baslangic_surecleri=ise_baslangic_surecleri, managers=potential_managers,
                           subeler=subeler, departmanlar=departmanlar, gorevler=gorevler)

@bp.route('/update/<int:calisan_id>', methods=('POST',))
@admin_required
def update(calisan_id):
    personnel = Personnel.query.get_or_404(calisan_id)
    form = request.form
    try:
        personnel.mail = form.get('mail')
        personnel.tel = form.get('tel')
        personnel.yakin_tel = form.get('yakin_tel')
        personnel.adres = form.get('adres')
        personnel.sube_id = form.get('sube_id')
        personnel.departman_id = form.get('departman_id')
        personnel.gorev_id = form.get('gorev_id')
        personnel.yaka_tipi = form.get('yaka_tipi')
        personnel.egitim = form.get('egitim')
        personnel.ucreti = form.get('ucreti')
        personnel.iban = form.get('iban')
        personnel.yonetici_id = form.get('yonetici_id') if form.get('yonetici_id') else None
        personnel.isten_cikis_tarihi = datetime.strptime(form.get('isten_cikis_tarihi'), '%Y-%m-%d').date() if form.get('isten_cikis_tarihi') else None
        personnel.aciklama = form.get('aciklama')

        db.session.commit()
        flash('Personel bilgileri başarıyla güncellendi.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"Güncelleme sırasında bir hata oluştu: {e}", 'danger')

    return redirect(url_for('personnel.manage', calisan_id=calisan_id))

@bp.route('/delete/<int:calisan_id>', methods=('POST',))
@admin_required
def delete(calisan_id):
    personnel = Personnel.query.get_or_404(calisan_id)
    try:
        personnel_upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], str(calisan_id))
        if os.path.exists(personnel_upload_path):
            shutil.rmtree(personnel_upload_path)

        db.session.delete(personnel)
        db.session.commit()
        flash('Personel ve ilişkili tüm verileri kalıcı olarak silindi.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Personel silinirken bir hata oluştu: {e}', 'danger')

    return redirect(url_for('personnel.list_personnel'))

@bp.route('/upload/<int:calisan_id>/<int:evrak_id>', methods=['POST'])
@login_required
def upload_file_route(calisan_id, evrak_id):
    evrak = Evrak.query.get_or_404(evrak_id)
    file = request.files.get('file')

    if not file or file.filename == '' or not allowed_file(file.filename):
        flash('Dosya seçilmedi veya geçersiz dosya türü.', 'danger')
        return redirect(url_for('personnel.manage', calisan_id=calisan_id))

    try:
        personnel_upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], str(calisan_id))
        os.makedirs(personnel_upload_path, exist_ok=True)

        safe_evrak_tipi = "".join(c for c in evrak.evrak_tipi if c.isalnum() or c in (' ', '_')).rstrip()
        filename = f"{safe_evrak_tipi.replace(' ', '_')}_{secure_filename(file.filename)}"

        file_path = os.path.join(personnel_upload_path, filename)
        file.save(file_path)

        evrak.dosya_yolu = os.path.join(str(calisan_id), filename)
        evrak.yuklendi_mi = True
        db.session.commit()
        flash(f"'{evrak.evrak_tipi}' belgesi başarıyla yüklendi.", 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Dosya yüklenirken bir hata oluştu: {e}', 'danger')

    return redirect(url_for('personnel.manage', calisan_id=calisan_id))

@bp.route('/uploads/<path:filename>')
@login_required
def uploaded_file(filename):
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)

@bp.route('/note/update/<int:evrak_id>', methods=['POST'])
@admin_required
def update_note(evrak_id):
    evrak = Evrak.query.get_or_404(evrak_id)
    try:
        evrak.notlar = request.form.get('notlar')
        db.session.commit()
        flash("Not başarıyla güncellendi.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Not güncellenirken bir hata oluştu: {e}", "danger")

    return redirect(url_for('personnel.manage', calisan_id=evrak.calisan_id))

@bp.route('/profile')
@login_required
@personnel_linked_required
def profile():
    # Düzeltme: current_user.personnel artık bir nesne, liste değil.
    personnel_info = current_user.personnel
    my_requests = personnel_info.izin_talepleri
    my_team = []
    if current_user.role in ['admin', 'manager']:
        my_team = Personnel.query.filter_by(yonetici_id=personnel_info.id, onay_durumu='Onaylandı').all()

    return render_template('profile.html', personnel=personnel_info, my_requests=my_requests, my_team=my_team)