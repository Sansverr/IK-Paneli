# app/dashboard.py

from flask import (
    Blueprint, render_template, request
)
from flask_login import login_required
from datetime import datetime, timedelta, date
from sqlalchemy import func, and_, or_, case

# Yeni SQLAlchemy yapısı için gerekli importlar
from .database import db, Personnel, LeaveRequest, Sube, Gorev, Evrak

bp = Blueprint('dashboard', __name__)

@bp.route('/')
@login_required
def index():
    """Tüm hesaplamaları yapan ve ana paneli gösteren ana fonksiyon."""
    try:
        # --- Tarih Filtrelemesi (Orijinal Mantık) ---
        current_year = int(request.args.get('year', datetime.now().year))
        current_month = int(request.args.get('month', datetime.now().month))

        start_of_month = date(current_year, current_month, 1)
        if current_month == 12:
            end_of_month = date(current_year + 1, 1, 1) - timedelta(days=1)
        else:
            end_of_month = date(current_year, current_month + 1, 1) - timedelta(days=1)

        aylar = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
        report_period_str = f"{aylar[current_month-1]} - {current_year}"

        # --- KPI Hesaplamaları (SQLAlchemy ile) ---

        # Dönem içinde aktif olan personeller için temel filtre
        active_in_period_filter = and_(
            Personnel.onay_durumu == 'Onaylandı',
            Personnel.ise_baslama_tarihi <= end_of_month,
            or_(
                Personnel.isten_cikis_tarihi == None,
                Personnel.isten_cikis_tarihi >= start_of_month
            )
        )

        active_personnel_count = Personnel.query.filter(active_in_period_filter).count()
        blue_collar_count = Personnel.query.filter(active_in_period_filter, Personnel.yaka_tipi == 'MAVİ YAKA').count()
        white_collar_count = Personnel.query.filter(active_in_period_filter, Personnel.yaka_tipi == 'BEYAZ YAKA').count()

        departures_this_month = Personnel.query.filter(
            Personnel.onay_durumu == 'Onaylandı',
            Personnel.isten_cikis_tarihi.between(start_of_month, end_of_month)
        ).count()

        start_of_month_personnel_count = Personnel.query.filter(
            Personnel.onay_durumu == 'Onaylandı',
            Personnel.ise_baslama_tarihi < start_of_month,
            or_(
                Personnel.isten_cikis_tarihi == None,
                Personnel.isten_cikis_tarihi >= start_of_month
            )
        ).count()

        turnover_rate = round((departures_this_month / start_of_month_personnel_count) * 100, 2) if start_of_month_personnel_count > 0 else 0
        pending_leave_requests_count = LeaveRequest.query.filter_by(durum='Beklemede').count()

        # --- Grafik Verileri (SQLAlchemy ile) ---

        company_data = db.session.query(Sube.sube_adi, func.count(Personnel.id)).join(Personnel).filter(active_in_period_filter).group_by(Sube.sube_adi).all()
        position_data = db.session.query(Gorev.gorev_adi, func.count(Personnel.id)).join(Personnel).filter(active_in_period_filter).group_by(Gorev.gorev_adi).all()

        # --- Widget Verileri (SQLAlchemy ile) ---

        # 5+ yıl çalışanlar
        five_years_ago = date.today() - timedelta(days=5*365.25)
        long_service_employees = Personnel.query.filter(
            Personnel.onay_durumu == 'Onaylandı',
            Personnel.isten_cikis_tarihi == None,
            Personnel.ise_baslama_tarihi <= five_years_ago
        ).all()

        # Eksik evraklı personel
        yuklenen_evrak_subquery = db.session.query(func.count(Evrak.id)).filter(Evrak.calisan_id == Personnel.id, Evrak.yuklendi_mi == True).scalar_subquery()
        toplam_evrak_subquery = db.session.query(func.count(Evrak.id)).filter(Evrak.calisan_id == Personnel.id).scalar_subquery()

        missing_docs_personnel = Personnel.query.filter(
            Personnel.onay_durumu == 'Onaylandı',
            Personnel.isten_cikis_tarihi == None,
            yuklenen_evrak_subquery < toplam_evrak_subquery
        ).order_by(yuklenen_evrak_subquery.asc()).limit(10).all()

        # Deneme süresi bitenler
        probation_period_days = 60
        today = date.today()
        thirty_days_later = today + timedelta(days=30)

        probation_ending_personnel = Personnel.query.filter(
            Personnel.onay_durumu == 'Onaylandı',
            Personnel.isten_cikis_tarihi == None,
            # Veritabanı fonksiyonu yerine Python'da hesaplama daha güvenilir
            # Bu sorgu tüm aktif personeli çeker ve Python'da filtrelenir
        ).all()

        probation_ending_list = []
        for p in probation_ending_personnel:
            if p.ise_baslama_tarihi:
                probation_end_date = p.ise_baslama_tarihi + timedelta(days=probation_period_days)
                if today <= probation_end_date <= thirty_days_later:
                    p.probation_end_date = probation_end_date # Geçici özellik ekle
                    probation_ending_list.append(p)

        # --- Tüm verileri şablona göndermek için hazırla ---
        dashboard_data = {
            "kpi": {
                "active_personnel": active_personnel_count, 
                "blue_collar": blue_collar_count, 
                "white_collar": white_collar_count, 
                "departures": departures_this_month, 
                "turnover_rate": turnover_rate, 
                "pending_leave_requests": pending_leave_requests_count
            },
            "company_chart": {"labels": [row[0] for row in company_data], "data": [row[1] for row in company_data]},
            "position_chart": {"labels": [row[0] for row in position_data], "data": [row[1] for row in position_data]},
            "long_service_employees": long_service_employees,
            "missing_docs_personnel": missing_docs_personnel,
            "probation_ending_personnel": probation_ending_list,
            "report_period": report_period_str,
            "selected_year": current_year,
            "selected_month": current_month
        }

    except Exception as e:
        flash(f"Dashboard verileri yüklenirken bir hata oluştu: {e}", "danger")
        # Hata durumunda boş bir yapı gönder
        dashboard_data = {
            "kpi": {"active_personnel": 0, "blue_collar": 0, "white_collar": 0, "departures": 0, "turnover_rate": 0, "pending_leave_requests": 0},
            "company_chart": {"labels": [], "data": []},
            "position_chart": {"labels": [], "data": []},
            "long_service_employees": [], "missing_docs_personnel": [], "probation_ending_personnel": [],
            "report_period": "Veri Alınamadı", "selected_year": datetime.now().year, "selected_month": datetime.now().month
        }

    return render_template('dashboard.html', data=dashboard_data)
