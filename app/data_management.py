import pandas as pd
import re
from flask import (
    Blueprint, flash, g, redirect, render_template, request, url_for
)
from app.auth import admin_required
import io
import csv

bp = Blueprint('data_management', __name__, url_prefix='/data_management')

def normalize_text(text):
    if not isinstance(text, str): return ""
    return text.upper().strip().replace('İ', 'I').replace('Ğ', 'G').replace('Ü', 'U').replace('Ş', 'S').replace('Ö', 'O').replace('Ç', 'C')

@bp.route('/', methods=['GET', 'POST'])
@admin_required
def manage():
    db = g.db
    if request.method == 'POST':
        entity = request.form.get('entity')
        name = request.form.get('name', '').strip().title()
        if not name: flash("İsim alanı boş bırakılamaz.", "danger")
        else:
            try:
                if entity == 'sube': db.execute("INSERT INTO subeler (sube_adi) VALUES (?)", (name,))
                elif entity == 'departman': db.execute("INSERT INTO departmanlar (departman_adi) VALUES (?)", (name,))
                elif entity == 'gorev': db.execute("INSERT INTO gorevler (gorev_adi) VALUES (?)", (name,))
                db.commit()
                flash(f"Yeni {entity} başarıyla eklendi.", "success")
            except db.IntegrityError:
                flash(f"Bu {entity} zaten mevcut.", "warning")
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
        if entity == 'sube': db.execute("DELETE FROM subeler WHERE id = ?", (entity_id,))
        elif entity == 'departman': db.execute("DELETE FROM departmanlar WHERE id = ?", (entity_id,))
        elif entity == 'gorev': db.execute("DELETE FROM gorevler WHERE id = ?", (entity_id,))
        db.commit()
        flash(f"{entity.capitalize()} başarıyla silindi.", "success")
    except Exception as e:
        flash(f"Silme işlemi sırasında bir hata oluştu: {e}", "danger")
    return redirect(url_for('data_management.manage'))

@bp.route('/import', methods=['POST'])
@admin_required
def import_excel():
    if 'excel_file' not in request.files:
        flash('Dosya seçilmedi.', 'danger')
        return redirect(url_for('data_management.manage'))
    file = request.files['excel_file']
    if file.filename == '':
        flash('Dosya seçilmedi.', 'danger')
        return redirect(url_for('data_management.manage'))

    filename = file.filename.lower()
    if filename.endswith(('.xlsx', '.xls', '.csv')):
        try:
            file_content = io.BytesIO(file.read())

            if filename.endswith('.csv'):
                sample = file_content.read(2048).decode('utf-8-sig')
                file_content.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=',;')
                    df = pd.read_csv(file_content, dtype=str, sep=dialect.delimiter, encoding='utf-8-sig').fillna('')
                except csv.Error:
                    file_content.seek(0)
                    df = pd.read_csv(file_content, dtype=str, sep=';', encoding='utf-8-sig').fillna('')
            else:
                df = pd.read_excel(file_content, dtype=str).fillna('')

            original_columns = df.columns.tolist()
            df.columns = [normalize_text(col) for col in df.columns]

            column_map = { key: None for key in ['TC_KIMLIK_NO', 'ADI', 'SOYADI', 'SICIL_NO', 'ISE_GIRIS_TARIHI', 'ISTEN_CIKIS_TARIHI', 'DOGUM_TARIHI', 'CINSIYETI', 'KAN_GRUBU', 'TELEFON', 'ADRES', 'IBAN', 'OGRENIM_DURUMU', 'UCRETI', 'IS_YERI', 'DEPARTMAN', 'GOREVI'] }

            for i, normalized_col in enumerate(df.columns):
                original_col = original_columns[i]
                if "TC" in normalized_col and "KIMLIK" in normalized_col: column_map['TC_KIMLIK_NO'] = original_col
                elif normalized_col == "ADI": column_map['ADI'] = original_col
                elif normalized_col == "SOYADI": column_map['SOYADI'] = original_col
                elif "SICIL" in normalized_col and "NO" in normalized_col: column_map['SICIL_NO'] = original_col
                elif "GIRIS" in normalized_col and "TAR" in normalized_col: column_map['ISE_GIRIS_TARIHI'] = original_col
                elif "CIK" in normalized_col and "TAR" in normalized_col: column_map['ISTEN_CIKIS_TARIHI'] = original_col
                elif "DOGUM" in normalized_col and "TARIHI" in normalized_col: column_map['DOGUM_TARIHI'] = original_col
                elif "CINSIYET" in normalized_col: column_map['CINSIYETI'] = original_col
                elif "KAN" in normalized_col and "GRUBU" in normalized_col: column_map['KAN_GRUBU'] = original_col
                elif "TELEFON" in normalized_col: column_map['TELEFON'] = original_col
                elif "ADRES" in normalized_col: column_map['ADRES'] = original_col
                elif "IBAN" in normalized_col: column_map['IBAN'] = original_col
                elif "OGRENIM" in normalized_col: column_map['OGRENIM_DURUMU'] = original_col
                elif "UCRET" in normalized_col: column_map['UCRETI'] = original_col
                elif "SIRKET" in normalized_col or ("IS" in normalized_col and "YERI" in normalized_col): column_map['IS_YERI'] = original_col
                elif "DEPARTMAN" in normalized_col: column_map['DEPARTMAN'] = original_col
                elif "GOREVI" in normalized_col: column_map['GOREVI'] = original_col

            if not column_map['TC_KIMLIK_NO']:
                flash(f"Dosyada 'TC KİMLİK NO' içeren bir sütun başlığı bulunamadı. Bulunan başlıklar: {original_columns}", "danger")
                return redirect(url_for('data_management.manage'))

            db = g.db
            added_count, updated_count, skipped_count = 0, 0, 0
            subeler = {row['sube_adi']: row['id'] for row in db.execute("SELECT * FROM subeler").fetchall()}
            departmanlar = {row['departman_adi']: row['id'] for row in db.execute("SELECT * FROM departmanlar").fetchall()}
            gorevler = {row['gorev_adi']: row['id'] for row in db.execute("SELECT * FROM gorevler").fetchall()}

            for index, row in df.iterrows():
                tc_kimlik_raw = row.get(column_map['TC_KIMLIK_NO'])
                tc_kimlik = ''.join(re.findall(r'\d', str(tc_kimlik_raw)))

                if len(tc_kimlik) != 11:
                    skipped_count += 1
                    continue

                ad = str(row.get(column_map['ADI'], '')).strip().title()
                soyad = str(row.get(column_map['SOYADI'], '')).strip().title()
                if not ad or not soyad:
                    skipped_count += 1
                    continue

                def get_or_create_id(entity_dict, table_name, column_name, value):
                    clean_value = str(value).strip().title() if value and pd.notna(value) else None
                    if clean_value and clean_value not in entity_dict:
                        cursor = db.execute(f"INSERT INTO {table_name} ({column_name}) VALUES (?)", (clean_value,))
                        entity_dict[clean_value] = cursor.lastrowid
                    return entity_dict.get(clean_value)

                sube_id = get_or_create_id(subeler, 'subeler', 'sube_adi', row.get(column_map['IS_YERI']))
                departman_id = get_or_create_id(departmanlar, 'departmanlar', 'departman_adi', row.get(column_map['DEPARTMAN']))
                gorev_id = get_or_create_id(gorevler, 'gorevler', 'gorev_adi', row.get(column_map['GOREVI']))
                personel = db.execute("SELECT id FROM calisanlar WHERE tc_kimlik = ?", (tc_kimlik,)).fetchone()

                params = {
                    'ad': ad, 'soyad': soyad, 'sicil_no': row.get(column_map['SICIL_NO']),
                    'ise_baslama_tarihi': row.get(column_map['ISE_GIRIS_TARIHI']), 'isten_cikis_tarihi': row.get(column_map['ISTEN_CIKIS_TARIHI']),
                    'dogum_tarihi': row.get(column_map['DOGUM_TARIHI']), 'cinsiyet': row.get(column_map['CINSIYETI']), 'kan_grubu': row.get(column_map['KAN_GRUBU']),
                    'tel': row.get(column_map['TELEFON']), 'adres': row.get(column_map['ADRES']), 'iban': row.get(column_map['IBAN']),
                    'egitim': row.get(column_map['OGRENIM_DURUMU']), 'ucreti': row.get(column_map['UCRETI']), 'sube_id': sube_id,
                    'departman_id': departman_id, 'gorev_id': gorev_id, 'tc_kimlik': tc_kimlik
                }

                if personel:
                    updated_count += 1
                    db.execute("""UPDATE calisanlar SET ad=:ad, soyad=:soyad, sicil_no=:sicil_no, ise_baslama_tarihi=:ise_baslama_tarihi, isten_cikis_tarihi=:isten_cikis_tarihi, dogum_tarihi=:dogum_tarihi, cinsiyet=:cinsiyet, kan_grubu=:kan_grubu, tel=:tel, adres=:adres, iban=:iban, egitim=:egitim, ucreti=:ucreti, sube_id=:sube_id, departman_id=:departman_id, gorev_id=:gorev_id WHERE tc_kimlik=:tc_kimlik""", params)
                else:
                    added_count += 1
                    db.execute("""INSERT INTO calisanlar (ad, soyad, sicil_no, ise_baslama_tarihi, isten_cikis_tarihi, dogum_tarihi, cinsiyet, kan_grubu, tel, adres, iban, egitim, ucreti, sube_id, departman_id, gorev_id, tc_kimlik) VALUES (:ad, :soyad, :sicil_no, :ise_baslama_tarihi, :isten_cikis_tarihi, :dogum_tarihi, :cinsiyet, :kan_grubu, :tel, :adres, :iban, :egitim, :ucreti, :sube_id, :departman_id, :gorev_id, :tc_kimlik)""", params)

            db.commit()
            flash_message = f"İşlem tamamlandı! {added_count} yeni personel eklendi, {updated_count} personel güncellendi."
            if skipped_count > 0:
                flash_message += f" {skipped_count} satır geçersiz veya boş anahtar bilgi (TC/Ad/Soyad) nedeniyle atlandı."
            flash(flash_message, "success")
        except Exception as e:
            flash(f"Dosya işlenirken bir hata oluştu: {e}", "danger")

        return redirect(url_for('data_management.manage'))

    flash("Lütfen geçerli bir Excel (.xlsx, .xls) veya CSV (.csv) dosyası seçin.", "warning")
    return redirect(url_for('data_management.manage'))