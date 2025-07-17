from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for
)
from app.auth import login_required, personnel_linked_required
from datetime import datetime

bp = Blueprint('leave', __name__, url_prefix='/leave')

@bp.route('/', methods=('GET', 'POST'))
@login_required
@personnel_linked_required
def management():
    db = g.db
    calisan_id = session.get('calisan_id')
    user_role = session.get('role')

    if request.method == 'POST':
        start_date_str = request.form['baslangic_tarihi']
        end_date_str = request.form['bitis_tarihi']
        leave_type = request.form['izin_tipi']
        aciklama = request.form['aciklama']
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
            if start_date > end_date:
                flash("Başlangıç tarihi, bitiş tarihinden sonra olamaz.", "danger")
                return redirect(url_for('leave.management'))
        except ValueError:
            flash("Geçersiz tarih formatı.", "danger")
            return redirect(url_for('leave.management'))

        day_diff = (end_date - start_date).days + 1
        current_personnel = db.execute('SELECT * FROM calisanlar WHERE id = ?', (calisan_id,)).fetchone()

        if leave_type == 'Yıllık İzin':
            if current_personnel['yillik_izin_bakiye'] < day_diff:
                flash(f"Yetersiz izin bakiyesi. Kalan izin: {current_personnel['yillik_izin_bakiye']} gün.", "danger")
                return redirect(url_for('leave.management'))
            new_balance = current_personnel['yillik_izin_bakiye'] - day_diff
            db.execute('UPDATE calisanlar SET yillik_izin_bakiye = ? WHERE id = ?', (new_balance, calisan_id))

        db.execute("INSERT INTO izin_talepleri (calisan_id, izin_tipi, baslangic_tarihi, bitis_tarihi, gun_sayisi, aciklama, talep_tarihi) VALUES (?, ?, ?, ?, ?, ?, ?)",
                   (calisan_id, leave_type, start_date_str, end_date_str, day_diff, aciklama, datetime.now().strftime('%Y-%m-%d')))
        db.commit()
        flash("İzin talebiniz başarıyla alınmıştır.", "success")
        return redirect(url_for('leave.management'))

    pending_requests = []
    if user_role == 'admin':
        pending_requests = db.execute("SELECT it.*, c.ad_soyad FROM izin_talepleri it JOIN calisanlar c ON it.calisan_id = c.id WHERE it.durum = 'Beklemede' ORDER BY it.talep_tarihi DESC").fetchall()
    elif user_role == 'manager':
        manager_personnel_id = session.get('calisan_id')
        if manager_personnel_id:
             pending_requests = db.execute("SELECT it.*, c.ad_soyad FROM izin_talepleri it JOIN calisanlar c ON it.calisan_id = c.id WHERE it.durum = 'Beklemede' AND c.yonetici_id = ? ORDER BY it.talep_tarihi DESC", (manager_personnel_id,)).fetchall()

    return render_template('leave_management.html', pending_requests=pending_requests)

@bp.route('/action/<int:request_id>/<string:action>', methods=('POST',))
@login_required
def leave_action(request_id, action):
    if session.get('role') not in ['admin', 'manager']:
        flash("Bu işlemi yapma yetkiniz yok.", "danger")
        return redirect(url_for('leave.management'))

    db = g.db
    leave_request = db.execute('SELECT * FROM izin_talepleri WHERE id = ?', (request_id,)).fetchone()
    if not leave_request:
        flash("İzin talebi bulunamadı.", "danger")
        return redirect(url_for('leave.management'))

    if action == 'approve':
        db.execute("UPDATE izin_talepleri SET durum = 'Onaylandı' WHERE id = ?", (request_id,))
        flash("İzin talebi onaylandı.", "success")
    elif action == 'reject':
        db.execute("UPDATE izin_talepleri SET durum = 'Reddedildi' WHERE id = ?", (request_id,))
        if leave_request['izin_tipi'] == 'Yıllık İzin':
            db.execute("UPDATE calisanlar SET yillik_izin_bakiye = yillik_izin_bakiye + ? WHERE id = ?", (leave_request['gun_sayisi'], leave_request['calisan_id']))
        flash("İzin talebi reddedildi.", "info")

    db.commit()
    return redirect(url_for('leave.management'))