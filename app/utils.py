# app/utils.py

import random
import string
import pandas as pd
import re
import io
from datetime import datetime

def generate_random_password(length=8):
    """Belirtilen uzunlukta rastgele bir şifre oluşturur."""
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for i in range(length))

def send_password_email(email, password):
    """Şifre gönderme işlemini simüle eder."""
    print(f"--> E-POSTA SİMÜLASYONU: Kime={email}, Yeni Şifre={password}")
    return True

def turkish_lower(text):
    """Türkçe karakterlere uygun şekilde küçük harfe çevirir."""
    if not isinstance(text, str): return ""
    return text.replace('İ', 'i').lower()

def to_turkish_title_case(s):
    """Türkçe karakterlere uygun şekilde baş harfleri büyük yazar."""
    if not isinstance(s, str): return ""
    words = []
    for word in s.split(' '):
        if not word: continue
        first_char, rest_of_word = word[0], word[1:]
        if first_char == 'i': first_char_upper = 'İ'
        elif first_char == 'ı': first_char_upper = 'I'
        else: first_char_upper = first_char.upper()
        rest_of_word_lower = rest_of_word.replace('İ', 'i').replace('I', 'ı').lower()
        words.append(first_char_upper + rest_of_word_lower)
    return ' '.join(words)

def format_date_field(date_input):
    """Tarih verisini YYYY-MM-DD formatına çevirir."""
    if pd.isna(date_input) or not date_input: return None
    try:
        return pd.to_datetime(date_input, errors='coerce', dayfirst=True).date()
    except Exception:
        return None

def normalize_header(header_text):
    """Excel başlıklarını standart bir formata getirir."""
    if not isinstance(header_text, str): return ""
    text = header_text.upper()
    replacements = {'İ': 'I', 'Ğ': 'G', 'Ü': 'U', 'Ş': 'S', 'Ö': 'O', 'Ç': 'C'}
    for char, replacement in replacements.items(): text = text.replace(char, replacement)
    return re.sub(r'[^A-Z0-9]', '', text)

def _read_file_to_dataframe(file):
    """Yüklenen dosyayı bir Pandas DataFrame'e okur."""
    file_content = io.BytesIO(file.read())
    if file.filename.lower().endswith('.csv'):
        return pd.read_csv(file_content, dtype=str, sep=',', encoding='utf-8-sig').fillna('')
    else:
        return pd.read_excel(file_content, dtype=str, engine='openpyxl').fillna('')

def _map_columns(columns):
    """Excel sütun başlıklarını veritabanı alan adlarıyla eşleştirir."""
    normalized_columns = {normalize_header(col): col for col in columns}
    column_map = {}
    mapping_keys = {
        'tc_kimlik': ["TCKIMLIKNO"], 'ad': ["ADI"], 'soyad': ["SOYADI"],
        'dogum_tarihi': ["DOGUMTARIHI"], 'cinsiyet': ["CINSIYETI"],
        'tel': ["CEPTELEFONU"], 'ise_baslama_tarihi': ["ISEGIRISTAR"],
        'isten_cikis_tarihi': ["ISTENCIKTAR"], 'sube': ["SUBE"],
        'gorev': ["GOREVI"], 'departman': ["MESLEKGRUBU(F1)", "DEPARTMAN(GRUP)"],
        'adres': ["ADRES"], 'iban': ["IBANNOPERSONEL"], 'ucreti': ["UCRET"],
        'sicil_no': ["SICILNO"], 'kan_grubu': ["KANGRUBU"], 'yakin_tel': ["YAKINTEL"],
        'egitim': ["EGITIMDURUMU"], 'yaka_tipi': ["YAKATIPI"]
    }
    for key, variations in mapping_keys.items():
        for var in variations:
            if var in normalized_columns:
                column_map[key] = normalized_columns[var]
                break
    return column_map
