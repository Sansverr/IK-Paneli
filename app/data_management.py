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

def turkish_lower(text):
    if not isinstance(text, str): return ""
    return text.replace('İ', 'i').lower()

def to_turkish_title_case(s):
    if not isinstance(s, str): return ""
    words = []
    for word in s.split(' '):
        if not word: continue
        first_char = word[0]
        rest_of_word = word[1:]
        if first_char == 'i': first_char_upper = 'İ'
        elif first_char == 'ı': first_char_upper = 'I'
        else: first_char_upper = first_char.upper()
        rest_of_word_lower = rest_of_word.replace('İ', 'i').replace('I', 'ı').lower()
        words.append(first_char_upper + rest_of_word_lower)
    return ' '.join(words)

def format_date_field(date_input):
    if pd.isna(date_input) or not date_input: return None
    try:
        date_obj = pd.to_datetime(date_input, errors='coerce', dayfirst=True)
        return date_obj.strftime('%Y-%m-%d') if not pd.isna(date_obj) else None
    except Exception: return None

def normalize_header(header_text):
    if not isinstance(header_text, str): return ""
    text = header_text.upper()
    replacements = {'İ': 'I', 'Ğ': 'G', 'Ü': 'U', 'Ş': 'S', 'Ö': 'O', 'Ç': 'C'}
    for char, replacement in replacements.items(): text = text.replace(char, replacement)
    return re.sub(r'[^A-Z0-9]', '', text)

@bp.route('/import', methods=['POST'])
@admin_required
def import_excel():
    if 'excel_file' not in request.files or not request.files['excel_file'].filename:
        flash('Dosya seçilmedi.', 'danger')
        return redirect(url_for('data_management.manage'))
    file = request.files['excel_file']
    if not file.filename.lower().endswith(('.xlsx', '.xls', '.csv')):
        flash("Lütfen geçerli bir Excel (.xlsx, .xls) veya CSV (.csv) dosyası seçin.", "warning")
        return redirect(url_for('data_management.manage'))
    try:
        newly_created_users = []
        db = g.db
        df = _read_file_to_dataframe(file)
        column_map = _map_columns(df.columns)
        if not column_map.get('tc_kimlik'):
            flash(f"Dosyada 'TC Kimlik No' içeren bir sütun başlığı bulunamadı. Bulunan başlıklar: {list(df.columns)}", "danger")
            return redirect(url_for('data_management.manage'))
        _prepare_related_data(db, df, column_map)
        personnel_to_add, personnel_to_update, skipped_count = _process_dataframe(db, df, column_map)
        if personnel_to_update:
            db.executemany("UPDATE calisanlar SET ad=?, soyad=?, sicil_no=?, ise_baslama_tarihi=?, isten_cikis_tarihi=?, dogum_tarihi=?, cinsiyet=?, kan_grubu=?, tel=?, yakin_tel=?, adres=?, iban=?, egitim=?, ucreti=?, sube_id=?, departman_id=?, gorev_id=? WHERE tc_kimlik=?", personnel_to_update)
        if personnel_to_add:
            db.executemany("INSERT OR IGNORE INTO calisanlar (ad, soyad, sicil_no, ise_baslama_tarihi, isten_cikis_tarihi, dogum_tarihi, cinsiyet, kan_grubu, tel, yakin_tel, adres, iban, egitim, ucreti, sube_id, departman_id, gorev_id, tc_kimlik, onay_durumu) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Onaylandı')", personnel_to_add)
            for p_data in personnel_to_add:
                personnel_name, tc_kimlik = f"{p_data[0]} {p_data[1]}", p_data[17]
                cursor = db.execute("SELECT id FROM calisanlar WHERE tc_kimlik=?", (tc_kimlik,))
                new_user_row = cursor.fetchone()
                if new_user_row and not db.execute("SELECT id FROM kullanicilar WHERE calisan_id=?", (new_user_row['id'],)).fetchone():
                    new_password = generate_random_password(8)
                    db.execute("INSERT INTO kullanicilar (password, role, calisan_id) VALUES (?, ?, ?)", (generate_password_hash(new_password), 'user', new_user_row['id']))
                    newly_created_users.append({'name': personnel_name, 'tc': tc_kimlik, 'password': new_password})
        db.commit()
        _flash_import_summary(len(personnel_to_add), len(personnel_to_update), skipped_count, newly_created_users)
    except Exception as e:
        db.rollback()
        flash(f"Dosya işlenirken beklenmedik bir hata oluştu: {e}", "danger")
    return redirect(url_for('data_management.manage'))

def _process_dataframe(db, df, column_map):
    existing_personnel_tcs = {row['tc_kimlik'] for row in db.execute("SELECT tc_kimlik FROM calisanlar")}
    subeler = {turkish_lower(row['sube_adi']): row['id'] for row in db.execute("SELECT id, sube_adi FROM subeler")}
    departmanlar = {turkish_lower(row['departman_adi']): row['id'] for row in db.execute("SELECT id, departman_adi FROM departmanlar")}
    gorevler = {turkish_lower(row['gorev_adi']): row['id'] for row in db.execute("SELECT id, gorev_adi FROM gorevler")}
    to_add, to_update, skipped = [], [], 0
    for _, row in df.iterrows():
        tc_kimlik = ''.join(re.findall(r'\d+', str(row.get(column_map.get('tc_kimlik'), ''))))
        ad, soyad = str(row.get(column_map.get('ad'), '')).strip(), str(row.get(column_map.get('soyad'), '')).strip()
        if not (tc_kimlik and len(tc_kimlik) == 11 and ad and soyad):
            skipped += 1
            continue
        data_tuple = _prepare_personnel_data(row, column_map, subeler, departmanlar, gorevler)
        if tc_kimlik in existing_personnel_tcs: to_update.append(data_tuple + (tc_kimlik,))
        else:
            to_add.append(data_tuple + (tc_kimlik,))
            existing_personnel_tcs.add(tc_kimlik)
    return to_add, to_update, skipped

def _prepare_personnel_data(row, column_map, subeler, departmanlar, gorevler):
    get_val = lambda key: row.get(column_map.get(key, ''), None)
    get_str = lambda key: str(get_val(key) or '').strip()
    return (to_turkish_title_case(get_str('ad')), to_turkish_title_case(get_str('soyad')), get_str('sicil_no') or None, format_date_field(get_val('ise_baslama_tarihi')), format_date_field(get_val('isten_cikis_tarihi')), format_date_field(get_val('dogum_tarihi')), to_turkish_title_case(get_str('cinsiyet')), get_str('kan_grubu'), get_str('tel'), get_str('yakin_tel'), get_str('adres'), get_str('iban'), to_turkish_title_case(get_str('egitim')), get_str('ucreti'), subeler.get(turkish_lower(get_str('sube'))), departmanlar.get(turkish_lower(get_str('departman'))), gorevler.get(turkish_lower(get_str('gorev'))))

def _prepare_related_data(db, df, column_map):
    def get_and_update_entities(entity_key, table, column):
        if column_map.get(entity_key):
            unique_values = {str(val).strip() for val in df[column_map[entity_key]].dropna() if str(val).strip()}
            if unique_values:
                db.executemany(f"INSERT OR IGNORE INTO {table} ({column}) VALUES (?)", [(to_turkish_title_case(val),) for val in unique_values])
                db.commit()
    get_and_update_entities('sube', 'subeler', 'sube_adi')
    get_and_update_entities('departman', 'departmanlar', 'departman_adi')
    get_and_update_entities('gorev', 'gorevler', 'gorev_adi')

def _map_columns(columns):
    normalized_columns, column_map = {normalize_header(col): col for col in columns}, {}
    mapping_keys = {'tc_kimlik': ["TCKIMLIKNO"], 'ad': ["ADI"], 'soyad': ["SOYADI"], 'dogum_tarihi': ["DOGUMTARIHI"], 'cinsiyet': ["CINSIYETI"], 'tel': ["CEPTELEFONU"], 'ise_baslama_tarihi': ["ISEGIRISTAR"], 'isten_cikis_tarihi': ["ISTENCIKTAR"], 'sube': ["SUBE"], 'gorev': ["GOREVI"], 'departman': ["MESLEKGRUBU(F1)", "DEPARTMAN(GRUP)"], 'adres': ["ADRES"], 'iban': ["IBANNOPERSONEL"], 'ucreti': ["UCRET"]}
    for key, variations in mapping_keys.items():
        for var in variations:
            if var in normalized_columns:
                column_map[key] = normalized_columns[var]
                break
    return column_map

def _read_file_to_dataframe(file):
    file_content = io.BytesIO(file.read())
    return pd.read_csv(file_content, dtype=str, sep=',', encoding='utf-8-sig').fillna('') if file.filename.lower().endswith('.csv') else pd.read_excel(file_content, dtype=str, engine='openpyxl').fillna('')

def _flash_import_summary(added, updated, skipped, new_users):
    summary = f"İşlem tamamlandı! {added} yeni personel eklendi, {updated} personel güncellendi."
    if skipped > 0: summary += f" {skipped} satır, geçersiz veya eksik TC/Ad/Soyad bilgisi nedeniyle atlandı."
    if new_users:
        passwords_html = "<ul>" + "".join(f"<li><b>{user['name']} (TC: {user['tc']}):</b> {user['password']}</li>" for user in new_users) + "</ul>"
        flash(f"{summary}<br><br><b>Yeni Personellerin Geçici Şifreleri:</b><br>{passwords_html}", "success")
    else: flash(summary, "success")

@bp.route('/', methods=['GET', 'POST'])
@admin_required
def manage():
    db = g.db
    if request.method == 'POST':
        entity = request.form.get('entity')
        name = str(request.form.get('name', '')).strip()
        if not name:
            flash("İsim alanı boş bırakılamaz.", "danger")
        else:
            table_map = {'sube': 'subeler', 'departman': 'departmanlar', 'gorev': 'gorevler', 'evrak': 'evrak_tipleri'}
            column_map = {'sube': 'sube_adi', 'departman': 'departman_adi', 'gorev': 'gorev_adi', 'evrak': 'evrak_adi'}
            proper_cased_name = to_turkish_title_case(name)
            if entity == 'evrak':
                kategori = request.form.get('kategori')
                db.execute(f"INSERT OR IGNORE INTO {table_map[entity]} ({column_map[entity]}, kategori) VALUES (?, ?)", (proper_cased_name, kategori))
            else:
                db.execute(f"INSERT OR IGNORE INTO {table_map[entity]} ({column_map[entity]}) VALUES (?)", (proper_cased_name,))
            db.commit()
            flash(f"'{proper_cased_name}' eklendi veya zaten mevcuttu.", "success")
        return redirect(url_for('data_management.manage'))
    subeler = db.execute("SELECT * FROM subeler ORDER BY sube_adi").fetchall()
    departmanlar = db.execute("SELECT * FROM departmanlar ORDER BY departman_adi").fetchall()
    gorevler = db.execute("SELECT * FROM gorevler ORDER BY gorev_adi").fetchall()
    evrak_tipleri = db.execute("SELECT * FROM evrak_tipleri ORDER BY kategori, evrak_adi").fetchall()
    return render_template('data_management.html', subeler=subeler, departmanlar=departmanlar, gorevler=gorevler, evrak_tipleri=evrak_tipleri)

@bp.route('/delete/<string:entity>/<int:entity_id>', methods=['POST'])
@admin_required
def delete(entity, entity_id):
    db = g.db
    try:
        table_map = {'sube': 'subeler', 'departman': 'departmanlar', 'gorev': 'gorevler', 'evrak': 'evrak_tipleri'}
        db.execute(f"DELETE FROM {table_map[entity]} WHERE id = ?", (entity_id,))
        db.commit()
        flash("Kayıt başarıyla silindi.", "success")
    except Exception as e:
        flash(f"Silme işlemi sırasında bir hata oluştu: Bu kaydı kullanan başka veriler olabilir. Hata: {e}", "danger")
    return redirect(url_for('data_management.manage'))