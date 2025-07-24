# app/leave.py

from flask import (
    Blueprint, flash, redirect, render_template, request, url_for
)
from flask_login import login_required, current_user
from datetime import datetime, date

# Yeni SQLAlchemy yapısı için gerekli importlar
from .database import db, LeaveRequest, Personnel
from .auth import admin_required, personnel_linked_required

bp = Blueprint('leave', __name__, url_prefix='/leave')

@bp.route('/', methods=('GET', 'POST'))
@login_required
@personnel_linked_required
def management():
    # POST: Yeni izin talebi oluşturma
    if request.method == 'POST':
        try:
            start_date_str = request.form['baslangic_tarihi']
            end_date_str = request.form['bitis_tarihi']
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

            if start_date > end_date:
                flash("Başlangıç tarihi, bitiş tarihinden sonra olamaz.", "danger")
                return redirect(url_for('leave.management'))

            day_diff = (end_date - start_date).days + 1
            personnel = current_user.personnel[0]
            leave_type = request.form['izin_tipi']

            # Orijinal mantık: Yıllık izin ise bakiye kontrolü yap ve düş
            if leave_type == 'Yıllık İzin':
                if personnel.yillik_izin_bakiye < day_diff:
                    flash(f"Yetersiz izin bakiyesi. Kalan izin: {personnel.yillik_izin_bakiye} gün.", "danger")
                    return redirect(url_for('leave.management'))
                # Not: Orijinal mantıkta bakiye talep anında düşülüyor.
                personnel.yillik_izin_bakiye -= day_diff

            new_request = LeaveRequest(
                personnel_id=personnel.id,
                leave_type=leave_type,
                start_date=start_date,
                end_date=end_date,
                gun_sayisi=day_diff,
                aciklama=request.form['aciklama'],
                talep_tarihi=date.today()
            )
            db.session.add(new_request)
            db.session.commit()
            flash("İzin talebiniz başarıyla alınmıştır.", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"İzin talebi oluşturulurken bir hata oluştu: {e}", "danger")

        return redirect(url_for('leave.management'))

    # GET: İzin taleplerini listeleme
    try:
        pending_requests = []
        # Admin tüm bekleyen talepleri görür
        if current_user.role == 'admin':
            pending_requests = LeaveRequest.query.filter_by(status='Beklemede').order_by(LeaveRequest.talep_tarihi.desc()).all()

        # 'manager' rolü, yönettiği kişilerin taleplerini görür
        elif current_user.role == 'manager':
            manager_personnel_id = current_user.personnel[0].id
            pending_requests = LeaveRequest.query.join(Personnel).filter(
                LeaveRequest.status == 'Beklemede',
                Personnel.yonetici_id == manager_personnel_id
            ).order_by(LeaveRequest.talep_tarihi.desc()).all()

    except Exception as e:
        flash(f"Bekleyen izin talepleri yüklenirken bir hata oluştu: {e}", "danger")
        pending_requests = []

    return render_template('leave_management.html', pending_requests=pending_requests)


@bp.route('/action/<int:request_id>/<string:action>', methods=('POST',))
@login_required
def leave_action(request_id, action):
    # Yetki kontrolü: Sadece admin ve manager bu işlemi yapabilir
    if current_user.role not in ['admin', 'manager']:
        flash("Bu işlemi yapma yetkiniz yok.", "danger")
        return redirect(url_for('dashboard.index'))

    leave_request = LeaveRequest.query.get_or_404(request_id)

    try:
        if action == 'approve':
            leave_request.status = 'Onaylandı'
            flash("İzin talebi onaylandı.", "success")
        elif action == 'reject':
            leave_request.status = 'Reddedildi'

            # Orijinal mantık: Reddedilen Yıllık İzin bakiyesini iade et
            if leave_request.leave_type == 'Yıllık İzin':
                personnel = leave_request.personnel
                personnel.yillik_izin_bakiye += leave_request.gun_sayisi
                flash("İzin talebi reddedildi ve yıllık izin bakiyesi iade edildi.", "info")
            else:
                flash("İzin talebi reddedildi.", "info")

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f"İşlem sırasında bir hata oluştu: {e}", "danger")

    return redirect(url_for('leave.management'))
