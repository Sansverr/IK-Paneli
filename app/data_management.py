# app/data_management.py

import pandas as pd
import re
import io
import csv
from flask import (
    Blueprint, flash, g, redirect, render_template, request, url_for
)
from werkzeug.security import generate_password_hash
from app.auth import admin_required
from app.utils import generate_random_password

bp = Blueprint('data_management', __name__, url_prefix='/data_management')

def normalize_header(header_text):
    """Sadece sütun başlıklarını eşleştirme için standart, boşluksuz bir formata getirir."""
    if not isinstance(header_text, str): return ""
    text = header_text.upper()
    replacements = {'İ': 'I', 'Ğ': 'G', 'Ü': 'U', 'Ş': 'S', 'Ö': 'O', 'Ç': 'C'}
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    return re.sub(r'[^A-Z0-9]', '', text)

# --- ANA VERİ İŞLEME FONKSİYONU ---
@bp.route('/import', methods=['POST'])
@admin_required
def import_excel():
    if 'excel_file' not in request.files or not request.files['excel_file'].filename:
        flash('Dosya seçilmedi.', 'danger')
        return redirect(url_for('data_management.manage'))

    file = request.files['excel_file']
    filename = file.filename.lower()

    if not filename.endswith(('.xlsx', '.xls', '.csv')):
        flash("Lütfen geçerli bir Excel (.xlsx, .xls) veya CSV (.csv) dosyası seçin.", "warning")
        return redirect(url_for('data_management.manage'))

    try:
        db = g.db
        df = _read_file_to_dataframe(file)
        column_map = _map_columns(df.columns)

        if not column_map.get('tc_kimlik'):
            flash(f"Dosyada 'TC Kimlik No' içeren bir sütun başlığı bulunamadı. Bulunan başlıklar: {list(df.columns)}", "danger")
            return redirect(url_for('data_management.manage'))

        _prepare_related_data(db, df, column_map)
        personnel_to_add, personnel_to_update, skipped_count = _process_dataframe(db, df, column_map)

        if personnel_to_update:
            db.executemany("""
                UPDATE calisanlar SET ad=?, soyad=?, sicil_no=?, ise_baslama_tarihi=?, isten_cikis_tarihi=?,
                dogum_tarihi=?, cinsiyet=?, kan_grubu=?, tel=?, yakin_tel=?, adres=?, iban=?, egitim=?, ucreti=?,
                sube_id=?, departman_id=?, gorev_id=? WHERE tc_kimlik=?
            """, personnel_to_update)

        newly_created_users = []
        if personnel_to_add:
            db.executemany("""
                INSERT INTO calisanlar (ad, soyad, sicil_no, ise_baslama_tarihi, isten_cikis_tarihi, dogum_tarihi,
                cinsiyet, kan_grubu, tel, yakin_tel, adres, iban, egitim, ucreti, sube_id, departman_id, gorev_id,
                tc_kimlik, onay_durumu)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Onaylandı')
            """, personnel_to_add)

            for p_data in personnel_to_add:
                personnel_name, tc_kimlik = f"{p_data[0]} {p_data[1]}", p_data[17]
                new_user_id = db.execute("SELECT id FROM calisanlar WHERE tc_kimlik=?", (tc_kimlik,)).fetchone()[0]
                new_password = generate_random_password(8)
                hashed_password = generate_password_hash(new_password)
                db.execute("INSERT INTO kullanicilar (password, role, calisan_id) VALUES (?, ?, ?)",
                           (hashed_password, 'user', new_user_id))
                newly_created_users.append({'name': personnel_name, 'tc': tc_kimlik, 'password': new_password})

        db.commit()
        _flash_import_summary(len(personnel_to_add), len(personnel_to_update), skipped_count, newly_created_users)

    except Exception as e:
        db.rollback()
        flash(f"Dosya işlenirken beklenmedik bir hata oluştu: {e}", "danger")

    return redirect(url_for('data_management.manage'))

# --- YARDIMCI FONKSİYONLAR ---

def _process_dataframe(db, df, column_map):
    """DataFrame'i işler ve eklenecek/güncellenecek personel listelerini döndürür."""
    existing_personnel_tcs = {row['tc_kimlik'] for row in db.execute("SELECT tc_kimlik FROM calisanlar")}

    subeler = {row['sube_adi']: row['id'] for row in db.execute("SELECT id, sube_adi FROM subeler")}
    departmanlar = {row['departman_adi']: row['id'] for row in db.execute("SELECT id, departman_adi FROM departmanlar")}
    gorevler = {row['gorev_adi']: row['id'] for row in db.execute("SELECT id, gorev_adi FROM gorevler")}

    to_add, to_update, skipped = [], [], 0

    for _, row in df.iterrows():
        tc_kimlik = ''.join(re.findall(r'\d', str(row.get(column_map.get('tc_kimlik'), ''))))
        ad = str(row.get(column_map.get('ad'), '')).strip()
        soyad = str(row.get(column_map.get('soyad'), '')).strip()

        if not (tc_kimlik and len(tc_kimlik) == 11 and ad and soyad):
            skipped += 1
            continue

        data_tuple = _prepare_personnel_data(row, column_map, subeler, departmanlar, gorevler)

        if tc_kimlik in existing_personnel_tcs:
            to_update.append(data_tuple + (tc_kimlik,))
        else:
            to_add.append(data_tuple + (tc_kimlik,))

    return to_add, to_update, skipped

def _prepare_personnel_data(row, column_map, subeler, departmanlar, gorevler):
    """Tek bir satırdaki veriyi alır, temizler, standartlaştırır ve veritabanı için hazırlar."""
    get = lambda key: str(row.get(column_map.get(key, ''), '') or '').strip()

    ad = get('ad').title()
    soyad = get('soyad').title()
    sube = get('sube').title() if get('sube') else None
    departman = get('departman').title() if get('departman') else None
    gorev = get('gorev').title() if get('gorev') else None
    cinsiyet = get('cinsiyet').title() if get('cinsiyet') else None
    adres = get('adres')
    egitim = get('egitim').title() if get('egitim') else None
    sicil_no = get('sicil_no') if get('sicil_no') else None

    sube_id = subeler.get(sube)
    departman_id = departmanlar.get(departman)
    gorev_id = gorevler.get(gorev)

    return (
        ad, soyad, sicil_no, get('ise_baslama_tarihi'), get('isten_cikis_tarihi'),
        get('dogum_tarihi'), cinsiyet, get('kan_grubu'), get('tel'), get('yakin_tel'),
        adres, get('iban'), egitim, get('ucreti'),
        sube_id, departman_id, gorev_id
    )

def _prepare_related_data(db, df, column_map):
    """Dosyadaki Şube, Departman, Görev gibi ilişkili verileri hazırlar ve DB'ye ekler."""
    def get_and_update_entities(entity_key, table, column):
        if column_map.get(entity_key):
            unique_values = [str(val).strip().title() for val in df[column_map[entity_key]].dropna().unique() if str(val).strip()]
            if unique_values:
                db.executemany(f"INSERT OR IGNORE INTO {table} ({column}) VALUES (?)", [(v,) for v in unique_values])
                db.commit()

    get_and_update_entities('sube', 'subeler', 'sube_adi')
    get_and_update_entities('departman', 'departmanlar', 'departman_adi')
    get_and_update_entities('gorev', 'gorevler', 'gorev_adi')

def _map_columns(columns):
    """Dosya sütunlarını veritabanı alanlarıyla daha hassas bir şekilde eşleştirir."""
    normalized_columns = {normalize_header(col): col for col in columns}
    column_map = {}

    mapping_keys = {
        'tc_kimlik': ["TCKIMLIKNO"], 'ad': ["ADI"], 'soyad': ["SOYADI"],
        'sicil_no': ["SICILNO"], 'ise_baslama_tarihi': ["ISEGIRISTAR"], 'isten_cikis_tarihi': ["ISTENCIKTAR"],
        'dogum_tarihi': ["DOGUMTARIHI"], 'cinsiyet': ["CINSIYETI"], 'kan_grubu': ["KANGRUBU"],
        'tel': ["CEPTELEFONU"], 'yakin_tel': ["ACILTELEFON"], 'adres': ["ADRES"], 'iban': ["IBANNO"], 
        'egitim': ["EGITIMDURUMU"], 'ucreti': ["NETUCRET"],
        'sube': ["SUBE"], 'departman': ["DEPARTMAN"], 'gorev': ["GOREVI"]
    }

    for key, variations in mapping_keys.items():
        for var in variations:
            if var in normalized_columns:
                column_map[key] = normalized_columns[var]
                break
    return column_map

def _read_file_to_dataframe(file):
    """Gelen dosyayı okuyup bir Pandas DataFrame'e dönüştürür."""
    file_content = io.BytesIO(file.read())
    if file.filename.lower().endswith('.csv'):
        return pd.read_csv(file_content, dtype=str, sep=';', encoding='utf-8-sig').fillna('')
    else:
        return pd.read_excel(file_content, dtype=str).fillna('')

def _flash_import_summary(added, updated, skipped, new_users):
    """İçe aktarma işlemi sonunda kullanıcıya özet bilgi gösterir."""
    summary = f"İşlem tamamlandı! {added} yeni personel eklendi, {updated} personel güncellendi."
    if skipped > 0:
        summary += f" {skipped} satır, geçersiz veya eksik TC/Ad/Soyad bilgisi nedeniyle atlandı."

    if new_users:
        passwords_html = "<ul>" + "".join(f"<li><b>{user['name']} (TC: {user['tc']}):</b> {user['password']}</li>" for user in new_users) + "</ul>"
        flash(f"{summary}<br><br><b>Yeni Personellerin Geçici Şifreleri:</b><br>{passwords_html}", "success")
    else:
        flash(summary, "success")

# Diğer Blueprint Rotaları (Değişiklik yok)
@bp.route('/', methods=['GET', 'POST'])
@admin_required
def manage():
    db = g.db
    if request.method == 'POST':
        entity = request.form.get('entity')
        name = request.form.get('name', '').strip().title()
        if not name:
            flash("İsim alanı boş bırakılamaz.", "danger")
        else:
            try:
                table_map = {'sube': 'subeler', 'departman': 'departmanlar', 'gorev': 'gorevler'}
                column_map = {'sube': 'sube_adi', 'departman': 'departman_adi', 'gorev': 'gorev_adi'}
                db.execute(f"INSERT INTO {table_map[entity]} ({column_map[entity]}) VALUES (?)", (name,))
                db.commit()
                flash(f"Yeni '{name}' başarıyla eklendi.", "success")
            except db.IntegrityError:
                flash(f"Bu '{name}' zaten mevcut.", "warning")
        return redirect(url_for('data_management.manage'))
    subeler = db.execute("SELECT * FROM subeler ORDER BY sube_adi").fetchall()
    departmanlar = db.execute("SELECT * FROM departmanlar ORDER BY departman_adi").fetchall()
    gorevler = db.execute("SELECT * FROM gorevler ORDER BY gorev_adi").fetchall()
    return render_template('data_management.html', subeler=subeler, departmanlar=departmanlar, gorevler=gorevler)

@bp.route('/delete/<string:entity>/<int:entity_id>', methods=['POST'])
@admin_required
def delete(entity, entity_id):
    db = g.db
    try:
        table_map = {'sube': 'subeler', 'departman': 'departmanlar', 'gorev': 'gorevler'}
        db.execute(f"DELETE FROM {table_map[entity]} WHERE id = ?", (entity_id,))
        db.commit()
        flash(f"{entity.capitalize()} başarıyla silindi.", "success")
    except Exception as e:
        flash(f"Silme işlemi sırasında bir hata oluştu: İlişkili personel kayıtları olabilir. Hata: {e}", "danger")
    return redirect(url_for('data_management.manage'))