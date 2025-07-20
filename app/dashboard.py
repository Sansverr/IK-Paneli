# app/dashboard.py

from flask import (
    Blueprint, render_template, request, session, g
)
from app.auth import login_required
from datetime import datetime, timedelta

bp = Blueprint('dashboard', __name__)

@bp.route('/')
@login_required
def index():
    return dashboard()

def dashboard():
    db = g.db
    cursor = db.cursor()

    try:
        current_year = int(request.args.get('year', datetime.now().year))
        current_month = int(request.args.get('month', datetime.now().month))
        if not (1 <= current_month <= 12):
            current_month = datetime.now().month
    except (ValueError, TypeError):
        current_year = datetime.now().year
        current_month = datetime.now().month

    start_of_month = datetime(current_year, current_month, 1)
    if current_month == 12:
        end_of_month = datetime(current_year + 1, 1, 1) - timedelta(days=1)
    else:
        end_of_month = datetime(current_year, current_month + 1, 1) - timedelta(days=1)

    start_date_str = start_of_month.strftime('%Y-%m-%d')
    end_date_str = end_of_month.strftime('%Y-%m-%d')

    aylar = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
    report_period_str = f"{aylar[current_month-1]} - {current_year}"

    active_in_period_condition = """
        onay_durumu = 'Onaylandı' AND ise_baslama_tarihi <= ?
        AND (isten_cikis_tarihi IS NULL OR isten_cikis_tarihi = '' OR isten_cikis_tarihi >= ?)
    """
    params = (end_date_str, start_date_str)

    active_personnel_count = cursor.execute(f"SELECT COUNT(id) FROM calisanlar WHERE {active_in_period_condition}", params).fetchone()[0]
    blue_collar_count = cursor.execute(f"SELECT COUNT(id) FROM calisanlar WHERE yaka_tipi = 'MAVİ YAKA' AND {active_in_period_condition}", params).fetchone()[0]
    white_collar_count = cursor.execute(f"SELECT COUNT(id) FROM calisanlar WHERE yaka_tipi = 'BEYAZ YAKA' AND {active_in_period_condition}", params).fetchone()[0]

    departures_this_month = cursor.execute("""
        SELECT COUNT(id) FROM calisanlar
        WHERE onay_durumu = 'Onaylandı' AND isten_cikis_tarihi BETWEEN ? AND ?
    """, (start_date_str, end_date_str)).fetchone()[0]

    start_of_month_personnel_count = cursor.execute("""
        SELECT COUNT(id) FROM calisanlar WHERE onay_durumu = 'Onaylandı' AND ise_baslama_tarihi < ?
        AND (isten_cikis_tarihi IS NULL OR isten_cikis_tarihi = '' OR isten_cikis_tarihi >= ?)
    """, (start_date_str, start_date_str)).fetchone()[0]

    turnover_rate = round((departures_this_month / start_of_month_personnel_count) * 100, 2) if start_of_month_personnel_count > 0 else 0
    pending_leave_requests_count = cursor.execute("SELECT COUNT(id) FROM izin_talepleri WHERE durum = 'Beklemede'").fetchone()[0]

    company_data = cursor.execute(f"SELECT s.sube_adi, COUNT(c.id) as count FROM calisanlar c JOIN subeler s ON c.sube_id = s.id WHERE {active_in_period_condition} GROUP BY s.sube_adi", params).fetchall()
    position_data = cursor.execute(f"SELECT g.gorev_adi, COUNT(c.id) as count FROM calisanlar c JOIN gorevler g ON c.gorev_id = g.id WHERE {active_in_period_condition} GROUP BY g.gorev_adi", params).fetchall()

    today = datetime.now()
    long_service_employees = []

    all_current_active_personnel = cursor.execute("SELECT id, ad, soyad, ise_baslama_tarihi FROM calisanlar WHERE (isten_cikis_tarihi IS NULL OR isten_cikis_tarihi = '') AND onay_durumu = 'Onaylandı'").fetchall()
    for p in all_current_active_personnel:
        try:
            hire_date = datetime.strptime(p['ise_baslama_tarihi'], '%Y-%m-%d')
            if (today - hire_date).days / 365.25 >= 5:
                long_service_employees.append(p)
        except (ValueError, TypeError): continue

    missing_docs_personnel = cursor.execute("SELECT c.id, c.ad, c.soyad, (SELECT COUNT(id) FROM evraklar WHERE calisan_id = c.id AND yuklendi_mi = 1) as yuklenen_evrak, (SELECT COUNT(id) FROM evraklar WHERE calisan_id = c.id) as toplam_evrak FROM calisanlar c WHERE (c.isten_cikis_tarihi IS NULL OR c.isten_cikis_tarihi = '') AND c.onay_durumu = 'Onaylandı' AND (SELECT COUNT(id) FROM evraklar WHERE calisan_id = c.id AND yuklendi_mi = 1) < (SELECT COUNT(id) FROM evraklar WHERE calisan_id = c.id) ORDER BY yuklenen_evrak ASC LIMIT 10").fetchall()

    probation_period_days = 60
    thirty_days_later = (today + timedelta(days=30)).strftime('%Y-%m-%d')
    today_str = today.strftime('%Y-%m-%d')
    probation_ending_personnel = cursor.execute("SELECT id, ad, soyad, ise_baslama_tarihi, DATE(ise_baslama_tarihi, '+' || ? || ' days') as probation_end_date FROM calisanlar WHERE (isten_cikis_tarihi IS NULL OR isten_cikis_tarihi = '') AND onay_durumu = 'Onaylandı' AND probation_end_date BETWEEN ? AND ? ORDER BY probation_end_date ASC", (str(probation_period_days), today_str, thirty_days_later)).fetchall()

    dashboard_data = {
        "kpi": {"active_personnel": active_personnel_count, "blue_collar": blue_collar_count, "white_collar": white_collar_count, "departures": departures_this_month, "turnover_rate": turnover_rate, "pending_leave_requests": pending_leave_requests_count},
        "company_chart": {"labels": [row['sube_adi'] for row in company_data], "data": [row['count'] for row in company_data]},
        "position_chart": {"labels": [row['gorev_adi'] for row in position_data], "data": [row['count'] for row in position_data]},
        "long_service_employees": long_service_employees,
        "missing_docs_personnel": missing_docs_personnel,
        "probation_ending_personnel": probation_ending_personnel,
        "report_period": report_period_str,
        "selected_year": current_year,
        "selected_month": current_month
    }
    return render_template('dashboard.html', data=dashboard_data)