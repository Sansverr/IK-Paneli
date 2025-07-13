from flask import Flask, render_template, request, redirect, url_for, g, flash, send_from_directory, session
import sqlite3
import os
from werkzeug.utils import secure_filename
from database import init_db, GEREKLI_EVRAKLAR
from datetime import datetime
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash

# Gerekli kütüphaneler
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import json
import io

# --- Uygulama Ayarları ---
DATABASE = 'hr.db'
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'xlsx'}

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'bu-cok-gizli-bir-anahtar-olmalı-ve-degistirilmeli')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- Kullanıcı Bilgileri (Not: Üretimde değiştirin) ---
KULLANICILAR = {
    "ik_uzmani": "GuvenliSifre123",
    "yonetici": "YoneticiSifre456"
}


# --- Veritabanı ve Yardımcı Fonksiyonlar (Değişiklik yok) ---
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

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Bu sayfayı görüntülemek için lütfen giriş yapın.", "warning")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- Mevcut Rotalar (Değişiklik yok) ---
# ('/', '/dashboard', '/personnel' vb. fonksiyonlar burada)
@app.route('/')
@login_required
def index():
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
@login_required
def dashboard():
    db = get_db()
    cursor = db.cursor()
    report_date = datetime.now()

    active_personnel_count = cursor.execute("SELECT COUNT(*) FROM calisanlar WHERE isten_cikis_tarihi IS NULL OR isten_cikis_tarihi = ''").fetchone()[0]
    blue_collar_count = cursor.execute("SELECT COUNT(*) FROM calisanlar WHERE yaka_tipi = 'MAVİ YAKA' AND (isten_cikis_tarihi IS NULL OR isten_cikis_tarihi = '')").fetchone()[0]
    white_collar_count = cursor.execute("SELECT COUNT(*) FROM calisanlar WHERE yaka_tipi = 'BEYAZ YAKA' AND (isten_cikis_tarihi IS NULL OR isten_cikis_tarihi = '')").fetchone()[0]

    departures_this_month = 0
    all_departures = cursor.execute("SELECT isten_cikis_tarihi FROM calisanlar WHERE isten_cikis_tarihi IS NOT NULL AND isten_cikis_tarihi != ''").fetchall()
    for row in all_departures:
        try:
            dep_date = datetime.strptime(row['isten_cikis_tarihi'], '%Y-%m-%d')
            if dep_date.month == report_date.month and dep_date.year == report_date.year:
                departures_this_month += 1
        except (ValueError, TypeError): continue

    turnover_rate = round((departures_this_month / active_personnel_count) * 100, 2) if active_personnel_count > 0 else 0

    cursor.execute("SELECT sube, COUNT(*) as count FROM calisanlar WHERE (isten_cikis_tarihi IS NULL OR isten_cikis_tarihi = '') AND sube IS NOT NULL GROUP BY sube")
    company_data = cursor.fetchall()

    cursor.execute("SELECT gorevi, COUNT(*) as count FROM calisanlar WHERE (isten_cikis_tarihi IS NULL OR isten_cikis_tarihi = '') AND gorevi IS NOT NULL GROUP BY gorevi")
    position_data = cursor.fetchall()

    long_service_employees = []
    all_active_personnel = cursor.execute("SELECT ad_soyad, ise_baslama_tarihi, gorevi, sube FROM calisanlar WHERE isten_cikis_tarihi IS NULL OR isten_cikis_tarihi = ''").fetchall()
    for p in all_active_personnel:
        try:
            hire_date = datetime.strptime(p['ise_baslama_tarihi'], '%Y-%m-%d')
            if (report_date - hire_date).days / 365.25 >= 5:
                long_service_employees.append(p)
        except (ValueError, TypeError): continue

    dashboard_data = {
        "kpi": {"active_personnel": active_personnel_count, "blue_collar": blue_collar_count, "white_collar": white_collar_count, "departures": departures_this_month, "turnover_rate": turnover_rate},
        "company_chart": {"labels": [row['sube'] for row in company_data if row['sube']], "data": [row['count'] for row in company_data if row['sube']]},
        "position_chart": {"labels": [row['gorevi'] for row in position_data if row['gorevi']], "data": [row['count'] for row in position_data if row['gorevi']]},
        "long_service_employees": long_service_employees
    }
    return render_template('dashboard.html', data=dashboard_data)

@app.route('/personnel')
@login_required
def personnel_list():
    calisanlar = get_db().execute("SELECT c.*, (SELECT COUNT(*) FROM evraklar WHERE calisan_id = c.id AND yuklendi_mi = 1) as yuklenen_evrak, (SELECT COUNT(*) FROM evraklar WHERE calisan_id = c.id) as toplam_evrak FROM calisanlar c ORDER BY c.id DESC").fetchall()
    return render_template('personnel_list.html', calisanlar=calisanlar)

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
            """INSERT INTO calisanlar (ad_soyad, ise_baslama_tarihi, sicil_no, sube, gorevi, tel, yakin_tel, tc_kimlik, adres, iban, egitim, ucreti, yaka_tipi)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (request.form['ad_soyad'], request.form['ise_baslama_tarihi'], sicil_no, request.form['sube'], request.form['gorevi'],
             request.form['tel'], request.form['yakin_tel'], request.form['tc_kimlik'], request.form['adres'],
             request.form['iban'], request.form['egitim'], request.form['ucreti'], request.form['yaka_tipi'])
        )
        new_id = cursor.lastrowid
        for evrak in GEREKLI_EVRAKLAR:
            cursor.execute('INSERT INTO evraklar (calisan_id, evrak_tipi) VALUES (?, ?)', (new_id, evrak))
        db.commit()
        flash(f"'{request.form['ad_soyad']}' adlı personel başarıyla eklendi.", 'success')
        return redirect(url_for('manage_personnel', calisan_id=new_id))
    return render_template('add_personnel.html')

@app.route('/personnel/manage/<int:calisan_id>')
@login_required
def manage_personnel(calisan_id):
    db = get_db()
    calisan = db.execute('SELECT * FROM calisanlar WHERE id = ?', (calisan_id,)).fetchone()
    evraklar = db.execute('SELECT * FROM evraklar WHERE calisan_id = ?', (calisan_id,)).fetchall()
    if not calisan: return "Personel bulunamadı", 404
    return render_template('personnel_manage.html', calisan=calisan, evraklar=evraklar)

@app.route('/personnel/update/<int:calisan_id>', methods=['POST'])
@login_required
def update_personnel(calisan_id):
    db = get_db()
    form = request.form
    db.execute("""
        UPDATE calisanlar SET ad_soyad=?, ise_baslama_tarihi=?, sicil_no=?, sube=?, gorevi=?, tel=?, yakin_tel=?,
        tc_kimlik=?, adres=?, iban=?, egitim=?, ucreti=?, aciklama=?, yaka_tipi=?, isten_cikis_tarihi=?
        WHERE id = ?""",
        (form['ad_soyad'], form['ise_baslama_tarihi'], form['sicil_no'], form['sube'], form['gorevi'], form['tel'],
         form['yakin_tel'], form['tc_kimlik'], form['adres'], form['iban'], form['egitim'], form['ucreti'],
         form['aciklama'], form['yaka_tipi'], form['isten_cikis_tarihi'], calisan_id)
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
# --- MALİYET ANALİZ ROTASI (HATA AYIKLAMA ODAKLI) ---
@app.route('/cost-analysis', methods=['GET', 'POST'])
@login_required
def cost_analysis():
    if request.method == 'POST':
        # --- 1. Adım: Temel Dosya Kontrolleri ---
        file = request.files.get('file')
        if not file or not file.filename:
            flash('Hata: Lütfen bir dosya seçin.', 'danger')
            return redirect(request.url)
        if not allowed_file(file.filename):
            flash('Hata: Geçersiz dosya türü. Lütfen .xlsx veya .csv dosyası yükleyin.', 'danger')
            return redirect(request.url)

        # --- 2. Adım: Excel Dosyasını Okuma ---
        try:
            # Excel dosyası için sabit olarak 4 satırı atla
            df = pd.read_excel(file, skiprows=4, engine='openpyxl')
            
            # Sütun isimlerini temizle
            df.columns = df.columns.str.strip()
            
            # Boş satırları temizle
            df = df.dropna(how='all')
            
            # Eğer hala boşsa, farklı satır sayısı ile deneme yap
            if df.empty or len(df.columns) < 3:
                file.seek(0)
                df = pd.read_excel(file, skiprows=3, engine='openpyxl')
                df.columns = df.columns.str.strip()
                df = df.dropna(how='all')
            
            # Son deneme - hiç satır atlamadan
            if df.empty or len(df.columns) < 3:
                file.seek(0)
                df = pd.read_excel(file, engine='openpyxl')
                df.columns = df.columns.str.strip()
                df = df.dropna(how='all')

            # Debug: Sütun isimlerini göster
            print("Dosyadaki sütunlar:", list(df.columns))
            print("Veri satır sayısı:", len(df))

        except Exception as e:
            flash(f"HATA: Dosya okunamadı! Teknik Hata: {e}", 'danger')
            return redirect(request.url)

        # --- 3. Adım: Veri İşleme ve Hesaplama ---
        try:
            # Dosyada bulunan sütun isimlerini kontrol et ve eşleştir
            available_columns = df.columns.tolist()
            
            # Dosyanızdaki sütun isimlerine göre doğrudan eşleştirme
            brut_sutun = None
            net_sutun = None
            personel_sutun = None
            departman_sutun = None
            pozisyon_sutun = None
            
            # Doğrudan sütun ismi eşleştirmesi
            if 'Brüt Toplam' in available_columns:
                brut_sutun = 'Brüt Toplam'
            elif 'Ücret' in available_columns:
                brut_sutun = 'Ücret'
                
            if 'Net Ücret' in available_columns:
                net_sutun = 'Net Ücret'
                
            if 'Adı Soyadı' in available_columns:
                personel_sutun = 'Adı Soyadı'
                
            if 'Masraf Merkezi' in available_columns:
                departman_sutun = 'Masraf Merkezi'
                
            if 'Görevi' in available_columns:
                pozisyon_sutun = 'Görevi'
            
            print(f"Eşleştirilen sütunlar: Brüt={brut_sutun}, Net={net_sutun}, Personel={personel_sutun}, Departman={departman_sutun}, Pozisyon={pozisyon_sutun}")

            # Temel kontroller
            if not brut_sutun:
                flash(f"HATA: Brüt ücret sütunu bulunamadı! 'Brüt Toplam' veya 'Ücret' sütunu aranıyor. Mevcut sütunlar: {', '.join(available_columns)}", 'danger')
                return redirect(request.url)
            if not net_sutun:
                flash(f"HATA: Net ücret sütunu bulunamadı! 'Net Ücret' sütunu aranıyor. Mevcut sütunlar: {', '.join(available_columns)}", 'danger')
                return redirect(request.url)
            if not personel_sutun:
                flash(f"HATA: Personel adı sütunu bulunamadı! 'Adı Soyadı' sütunu aranıyor. Mevcut sütunlar: {', '.join(available_columns)}", 'danger')
                return redirect(request.url)
            
            print(f"Tüm kontroller başarılı! Hesaplamalara geçiliyor...")

            # Sayısal dönüşüm fonksiyonu
            def clean_numeric(series):
                return pd.to_numeric(
                    series.astype(str)
                    .str.replace('.', '', regex=False)
                    .str.replace(',', '.', regex=False)
                    .str.replace('TL', '', regex=False)
                    .str.replace('₺', '', regex=False)
                    .str.replace(' ', '', regex=False)
                    .str.strip(),
                    errors='coerce'
                ).fillna(0)

            # Sayısal dönüşümler
            print(f"Brüt sütun örnek değerler (ilk 5): {df[brut_sutun].head().tolist()}")
            df[brut_sutun] = clean_numeric(df[brut_sutun])
            df[net_sutun] = clean_numeric(df[net_sutun])
            print(f"Dönüştürülmüş brüt örnek değerler (ilk 5): {df[brut_sutun].head().tolist()}")
            print(f"Toplam geçerli brüt ücret sayısı: {(df[brut_sutun] > 0).sum()}")

            # Hesaplamalar
            df['SGK İşveren Payı (%15.5)'] = df[brut_sutun] * 0.155
            df['İşsizlik İşveren Payı (%2)'] = df[brut_sutun] * 0.02
            df['Toplam Personel Maliyeti'] = df[brut_sutun] + df['SGK İşveren Payı (%15.5)'] + df['İşsizlik İşveren Payı (%2)']

        except Exception as e:
            flash(f"HATA: Veri işlenirken bir sorun oluştu. Teknik Hata: {e}", 'danger')
            return redirect(request.url)

        # --- 4. Adım: Raporu ve Grafikleri Oluşturma ---
        try:
            print("Rapor oluşturma aşamasına geçiliyor...")
            
            # Sadece geçerli verileri al (brüt ücret > 0 olanlar)
            df_valid = df[df[brut_sutun] > 0]
            print(f"Geçerli veri sayısı: {len(df_valid)}")
            
            # KPI'ları hazırla
            total_employees = len(df_valid)
            total_net_pay = df_valid[net_sutun].sum()
            total_employer_cost = df_valid['Toplam Personel Maliyeti'].sum()
            print(f"KPI'lar hesaplandı: Personel={total_employees}, Net Pay={total_net_pay}, Employer Cost={total_employer_cost}")

            # Grafik oluşturma aşaması
            print("Pasta grafiği oluşturuluyor...")
            pie_labels = ['Personel Net Hakedişleri', 'Vergi ve Yasal Yükümlülükler']
            pie_values = [total_net_pay, total_employer_cost - total_net_pay]
            
            # Plotly grafik oluşturma yerine basit veri kullan
            cost_pie_json = json.dumps({
                "data": [{
                    "labels": pie_labels,
                    "values": pie_values,
                    "type": "pie",
                    "hole": 0.4,
                    "textinfo": "percent+label",
                    "marker": {"colors": ["#008080", "#D2691E"]}
                }],
                "layout": {
                    "title": "İşveren Maliyet Kırılımı"
                }
            })
            print("Pasta grafiği hazırlandı")

            # Departman ve Pozisyon analizleri - basitleştirilmiş
            dept_chart_json, pos_chart_json = None, None
            
            if departman_sutun and departman_sutun in df_valid.columns:
                print("Departman analizi yapılıyor...")
                dept_analizi = df_valid.groupby(departman_sutun)['Toplam Personel Maliyeti'].sum().sort_values(ascending=True).reset_index()
                if len(dept_analizi) > 0 and len(dept_analizi) <= 20:  # Çok fazla kategori varsa skip et
                    dept_chart_json = json.dumps({
                        "data": [{
                            "x": dept_analizi['Toplam Personel Maliyeti'].tolist(),
                            "y": dept_analizi[departman_sutun].tolist(),
                            "type": "bar",
                            "orientation": "h",
                            "marker": {"color": "#008080"}
                        }],
                        "layout": {
                            "title": "Departman Bazlı Toplam Maliyetler",
                            "xaxis": {"title": "Toplam Maliyet (TL)"},
                            "yaxis": {"title": "Departman"}
                        }
                    })
                    print("Departman grafiği hazırlandı")

            if pozisyon_sutun and pozisyon_sutun in df_valid.columns:
                print("Pozisyon analizi yapılıyor...")
                pos_analizi = df_valid.groupby(pozisyon_sutun)['Toplam Personel Maliyeti'].sum().sort_values(ascending=True).reset_index()
                if len(pos_analizi) > 0 and len(pos_analizi) <= 20:  # Çok fazla kategori varsa skip et
                    pos_chart_json = json.dumps({
                        "data": [{
                            "x": pos_analizi['Toplam Personel Maliyeti'].tolist(),
                            "y": pos_analizi[pozisyon_sutun].tolist(),
                            "type": "bar",
                            "orientation": "h",
                            "marker": {"color": "#D2691E"}
                        }],
                        "layout": {
                            "title": "Pozisyon Bazlı Toplam Maliyetler",
                            "xaxis": {"title": "Toplam Maliyet (TL)"},
                            "yaxis": {"title": "Pozisyon"}
                        }
                    })
                    print("Pozisyon grafiği hazırlandı")

            # Tabloları hazırla
            print("Tablolar hazırlanıyor...")
            gosterilecek_sutunlar = [personel_sutun]
            if departman_sutun: gosterilecek_sutunlar.append(departman_sutun)
            if pozisyon_sutun: gosterilecek_sutunlar.append(pozisyon_sutun)
            gosterilecek_sutunlar.extend([brut_sutun, net_sutun, 'Toplam Personel Maliyeti'])
            
            # Tablo oluştururken hata kontrolü
            try:
                top_10_table = df_valid.sort_values(by='Toplam Personel Maliyeti', ascending=False).head(10)[gosterilecek_sutunlar]
                top_10_table_html = top_10_table.to_html(classes='min-w-full bg-white divide-y divide-gray-200', border=0, index=False, float_format='{:,.2f}'.format)
                
                full_table_html = df_valid[gosterilecek_sutunlar].to_html(classes='min-w-full bg-white divide-y divide-gray-200', border=0, index=False, float_format='{:,.2f}'.format)
                print("Tablolar başarıyla oluşturuldu")
            except Exception as table_error:
                print(f"Tablo oluşturma hatası: {table_error}")
                # Sadece temel sütunlarla dene
                basic_columns = [personel_sutun, brut_sutun, net_sutun, 'Toplam Personel Maliyeti']
                top_10_table = df_valid.sort_values(by='Toplam Personel Maliyeti', ascending=False).head(10)[basic_columns]
                top_10_table_html = top_10_table.to_html(classes='min-w-full bg-white', border=0, index=False)
                full_table_html = df_valid[basic_columns].to_html(classes='min-w-full bg-white', border=0, index=False)

            # Sonuçları şablona göndermek için paketle
            report_data = {
                "kpi": { 
                    "total_employees": total_employees, 
                    "total_net_pay": f"{total_net_pay:,.2f}", 
                    "total_employer_cost": f"{total_employer_cost:,.2f}" 
                },
                "cost_pie_json": cost_pie_json,
                "dept_chart_json": dept_chart_json,
                "pos_chart_json": pos_chart_json,
                "top_10_table": top_10_table_html,
                "full_table": full_table_html
            }

            print("Rapor verisi hazırlandı, template'e gönderiliyor...")
            flash(f'Rapor başarıyla oluşturuldu! {total_employees} personel için analiz tamamlandı.', 'success')
            return render_template('cost_analysis.html', report_data=report_data)

        except Exception as e:
            print(f"Rapor oluşturma sırasında kritik hata: {e}")
            import traceback
            print(f"Hata detayı: {traceback.format_exc()}")
            flash(f"HATA: Rapor oluşturulurken bir sorun çıktı. Teknik Hata: {str(e)}", 'danger')
            return redirect(request.url)

    # GET request için boş sayfa
    return render_template('cost_analysis.html', report_data=None)


# --- Login / Logout Rotaları ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username in KULLANICILAR and KULLANICILAR[username] == password:
            session['user_id'] = username
            session['username'] = username
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
    app.run(host='0.0.0.0', port=8080, debug=True)