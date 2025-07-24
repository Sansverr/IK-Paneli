# app/data_management.py

import re
from flask import (
    Blueprint, flash, redirect, render_template, request, url_for
)
from werkzeug.security import generate_password_hash
import pandas as pd

from .database import db, Personnel, User, Departman, Sube, Gorev, EvrakTipi, Evrak
from .auth import admin_required
from .utils import (
    generate_random_password, turkish_lower, to_turkish_title_case, 
    format_date_field, _read_file_to_dataframe, _map_columns
)

bp = Blueprint('data_management', __name__, url_prefix='/data_management')

@bp.route('/', methods=['GET', 'POST'])
@admin_required
def manage():
    if request.method == 'POST':
        entity = request.form.get('entity')
        name = str(request.form.get('name', '')).strip()
        if not name:
            flash("İsim alanı boş bırakılamaz.", "danger")
        else:
            proper_cased_name = to_turkish_title_case(name)
            model_map = {'sube': Sube, 'departman': Departman, 'gorev': Gorev, 'evrak': EvrakTipi}
            column_map = {'sube': 'sube_adi', 'departman': 'departman_adi', 'gorev': 'gorev_adi', 'evrak': 'evrak_adi'}
            Model, column_name = model_map.get(entity), column_map.get(entity)
            if Model and column_name:
                if not Model.query.filter(getattr(Model, column_name).ilike(proper_cased_name)).first():
                    new_item = Model(**{column_name: proper_cased_name}) if entity != 'evrak' else Model(evrak_adi=proper_cased_name, kategori=request.form.get('kategori'))
                    db.session.add(new_item)
                    db.session.commit()
                    flash(f"'{proper_cased_name}' başarıyla eklendi.", "success")
                else:
                    flash(f"'{proper_cased_name}' zaten mevcut.", "warning")
        return redirect(url_for('data_management.manage'))

    subeler, departmanlar, gorevler, evrak_tipleri = Sube.query.order_by(Sube.sube_adi).all(), Departman.query.order_by(Departman.departman_adi).all(), Gorev.query.order_by(Gorev.gorev_adi).all(), EvrakTipi.query.order_by(EvrakTipi.kategori, EvrakTipi.evrak_adi).all()
    return render_template('data_management.html', subeler=subeler, departmanlar=departmanlar, gorevler=gorevler, evrak_tipleri=evrak_tipleri)

@bp.route('/delete/<string:entity>/<int:entity_id>', methods=['POST'])
@admin_required
def delete(entity, entity_id):
    model_map = {'sube': Sube, 'departman': Departman, 'gorev': Gorev, 'evrak': EvrakTipi}
    Model = model_map.get(entity)
    if not Model:
        flash("Geçersiz model türü.", "danger")
        return redirect(url_for('data_management.manage'))

    item_to_delete = Model.query.get_or_404(entity_id)
    try:
        db.session.delete(item_to_delete)
        db.session.commit()
        flash("Kayıt başarıyla silindi.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Silme işlemi sırasında bir hata oluştu: Bu kaydı kullanan başka veriler olabilir. Hata: {e}", "danger")
    return redirect(url_for('data_management.manage'))

@bp.route('/import', methods=['POST'])
@admin_required
def import_excel():
    file = request.files.get('excel_file')
    if not file or not file.filename:
        flash('Dosya seçilmedi.', 'danger')
        return redirect(url_for('data_management.manage'))
    if not file.filename.lower().endswith(('.xlsx', '.xls', '.csv')):
        flash("Lütfen geçerli bir Excel (.xlsx, .xls) veya CSV (.csv) dosyası seçin.", "warning")
        return redirect(url_for('data_management.manage'))

    try:
        df = _read_file_to_dataframe(file)
        column_map = _map_columns(df.columns)
        if not column_map.get('tc_kimlik'):
            flash(f"Dosyada 'TC Kimlik No' içeren bir sütun başlığı bulunamadı.", "danger")
            return redirect(url_for('data_management.manage'))

        _prepare_related_data(df, column_map)

        existing_personnel = {p.tc_kimlik: p for p in Personnel.query.all()}
        subeler = {turkish_lower(s.sube_adi): s.id for s in Sube.query.all()}
        departmanlar = {turkish_lower(d.departman_adi): d.id for d in Departman.query.all()}
        gorevler = {turkish_lower(g.gorev_adi): g.id for g in Gorev.query.all()}

        added_count, updated_count, skipped_count = 0, 0, 0
        newly_created_users = []

        for _, row in df.iterrows():
            tc_kimlik = ''.join(re.findall(r'\d+', str(row.get(column_map.get('tc_kimlik'), ''))))
            ad = str(row.get(column_map.get('ad'), '')).strip()
            soyad = str(row.get(column_map.get('soyad'), '')).strip()

            if not (tc_kimlik and len(tc_kimlik) == 11):
                skipped_count += 1
                continue

            if tc_kimlik in existing_personnel:
                personnel_to_update = existing_personnel[tc_kimlik]
                updates_made = _update_personnel_from_row(personnel_to_update, row, column_map, subeler, departmanlar, gorevler)
                if updates_made:
                    updated_count += 1
            else:
                if not (ad and soyad):
                    skipped_count += 1
                    continue
                personnel_data = _prepare_personnel_data(row, column_map, subeler, departmanlar, gorevler)

                # --- NİHAİ DÜZELTME: Yeni personel için kullanıcı hesabı ve evraklar oluşturuluyor ---
                new_personnel = Personnel(tc_kimlik=tc_kimlik, **personnel_data, onay_durumu='Onaylandı')

                # Kullanıcı oluştur
                new_password = generate_random_password(8)
                new_user = User(username=tc_kimlik, personnel=new_personnel)
                new_user.set_password(new_password)

                db.session.add(new_personnel)
                db.session.add(new_user)

                # Veritabanına personel eklendikten sonra ID'sini alabilmek için flush et
                db.session.flush()

                # Yeni personel için varsayılan evrakları oluştur
                gerekli_evraklar = EvrakTipi.query.all()
                for evrak_tipi in gerekli_evraklar:
                    yeni_evrak = Evrak(calisan_id=new_personnel.id, evrak_tipi=evrak_tipi.evrak_adi, kategori=evrak_tipi.kategori)
                    db.session.add(yeni_evrak)

                newly_created_users.append({'name': f"{ad} {soyad}", 'tc': tc_kimlik, 'password': new_password})
                added_count += 1

        db.session.commit()
        _flash_import_summary(added_count, updated_count, skipped_count, newly_created_users)
    except Exception as e:
        db.session.rollback()
        flash(f"Dosya işlenirken beklenmedik bir hata oluştu: {e}", "danger")
    return redirect(url_for('data_management.manage'))

def _prepare_related_data(df, column_map):
    """Excel'deki Şube, Departman ve Görevleri veritabanına ekler (mükerrer kontrolü ile)."""
    def get_and_update(entity_key, Model, column_name):
        if column_map.get(entity_key):
            unique_values_from_excel = {str(val).strip() for val in df[column_map[entity_key]].dropna() if str(val).strip()}
            existing_values = {turkish_lower(getattr(e, column_name)) for e in Model.query.all()}

            values_to_add = {val for val in unique_values_from_excel if turkish_lower(val) not in existing_values}

            for val in values_to_add:
                new_item = Model(**{column_name: to_turkish_title_case(val)})
                db.session.add(new_item)

            if values_to_add:
                db.session.commit()

    get_and_update('sube', Sube, 'sube_adi')
    get_and_update('departman', Departman, 'departman_adi')
    get_and_update('gorev', Gorev, 'gorev_adi')

def _prepare_personnel_data(row, column_map, subeler, departmanlar, gorevler):
    """DataFrame satırından yeni bir personel için veri sözlüğü oluşturur."""
    get_val = lambda key: row.get(column_map.get(key, ''), None)
    get_str = lambda key: str(get_val(key) or '').strip()
    return {
        'ad': to_turkish_title_case(get_str('ad')), 'soyad': to_turkish_title_case(get_str('soyad')),
        'sicil_no': get_str('sicil_no') or None, 'ise_baslama_tarihi': format_date_field(get_val('ise_baslama_tarihi')),
        'isten_cikis_tarihi': format_date_field(get_val('isten_cikis_tarihi')), 'dogum_tarihi': format_date_field(get_val('dogum_tarihi')),
        'cinsiyet': to_turkish_title_case(get_str('cinsiyet')), 'kan_grubu': get_str('kan_grubu'),
        'tel': get_str('tel'), 'yakin_tel': get_str('yakin_tel'), 'adres': get_str('adres'), 'iban': get_str('iban'),
        'egitim': to_turkish_title_case(get_str('egitim')), 'ucreti': get_str('ucreti'),
        'sube_id': subeler.get(turkish_lower(get_str('sube'))), 'departman_id': departmanlar.get(turkish_lower(get_str('departman'))),
        'gorev_id': gorevler.get(turkish_lower(get_str('gorev'))), 'yaka_tipi': get_str('yaka_tipi')
    }

def _update_personnel_from_row(personnel, row, column_map, subeler, departmanlar, gorevler):
    """Mevcut bir personeli Excel satırındaki dolu verilerle günceller."""
    updates_made = False
    data_to_check = _prepare_personnel_data(row, column_map, subeler, departmanlar, gorevler)

    for key, value in data_to_check.items():
        if value is not None and getattr(personnel, key) != value:
            setattr(personnel, key, value)
            updates_made = True
    return updates_made

def _flash_import_summary(added, updated, skipped, new_users):
    """İçe aktarma işlemi sonrası özet mesajı oluşturur."""
    summary = f"İşlem tamamlandı! {added} yeni personel eklendi, {updated} personel güncellendi."
    if skipped > 0: summary += f" {skipped} satır, geçersiz veya eksik TC bilgisi nedeniyle atlandı."
    if new_users:
        passwords_html = "<ul>" + "".join(f"<li><b>{user['name']} (TC: {user['tc']}):</b> {user['password']}</li>" for user in new_users) + "</ul>"
        flash(f"{summary}<br><br><b>Yeni Personellerin Geçici Şifreleri:</b><br>{passwords_html}", "success")
    else: flash(summary, "success")