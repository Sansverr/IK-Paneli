# app/admin.py

from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for
)
from werkzeug.security import generate_password_hash
from .auth import admin_required
from .utils import generate_random_password, send_password_email
from datetime import datetime

bp = Blueprint('admin', __name__, url_prefix='/admin')

@bp.route('/users')
@admin_required
def user_management():
    db = g.db
    requests_count = db.execute("SELECT COUNT(id) FROM sifre_sifirlama_talepleri WHERE durum = 'Beklemede'").fetchone()[0]
    users = db.execute("SELECT u.id, u.role, c.ad_soyad, c.tc_kimlik FROM kullanicilar u JOIN calisanlar c ON u.calisan_id = c.id ORDER BY c.ad_soyad").fetchall()
    unlinked_personnel = db.execute("SELECT * FROM calisanlar WHERE id NOT IN (SELECT calisan_id FROM kullanicilar WHERE calisan_id IS NOT NULL) AND onay_durumu = 'Onaylandı'").fetchall()
    return render_template('user_management.html', users=users, password_requests_count=requests_count, unlinked_personnel=unlinked_personnel)

@bp.route('/users/add', methods=('POST',))
@admin_required
def add_user():
    db = g.db
    calisan_id = request.form.get('calisan_id')
    role = request.form.get('role', 'user')

    if not calisan_id:
        flash("Lütfen bir personel seçin.", "danger")
        return redirect(url_for('admin.user_management'))

    existing_user = db.execute("SELECT id FROM kullanicilar WHERE calisan_id = ?", (calisan_id,)).fetchone()
    if existing_user:
        flash("Seçilen personel için zaten bir kullanıcı hesabı mevcut.", "warning")
        return redirect(url_for('admin.user_management'))

    default_password = generate_random_password(8)
    hashed_password = generate_password_hash(default_password)

    db.execute("INSERT INTO kullanicilar (password, role, calisan_id) VALUES (?, ?, ?)", (hashed_password, role, calisan_id))
    db.commit()
    flash(f"Personele başarıyla kullanıcı hesabı oluşturuldu. İletilmesi gereken şifre: {default_password}", "success")
    return redirect(url_for('admin.user_management'))

@bp.route('/users/edit/<int:user_id>', methods=('GET', 'POST'))
@admin_required
def edit_user(user_id):
    db = g.db
    user = db.execute("SELECT u.id, u.role, c.ad_soyad, c.mail FROM kullanicilar u JOIN calisanlar c ON u.calisan_id = c.id WHERE u.id = ?", (user_id,)).fetchone()

    if not user:
        flash("Kullanıcı bulunamadı.", "danger")
        return redirect(url_for('admin.user_management'))

    if request.method == 'POST':
        new_role = request.form.get('role')
        if user_id == session.get('user_id') and new_role != session.get('role'):
            flash('Kendi yetkinizi değiştiremezsiniz.', 'danger')
        else:
            db.execute("UPDATE kullanicilar SET role = ? WHERE id = ?", (new_role, user_id))
            db.commit()
            flash(f"'{user['ad_soyad']}' adlı kullanıcının yetkisi güncellendi.", "success")
        return redirect(url_for('admin.user_management'))

    return render_template('edit_user.html', user=user)

@bp.route('/users/delete/<int:user_id>', methods=('POST',))
@admin_required
def delete_user(user_id):
    if user_id == session['user_id']:
        flash('Kendi hesabınızı silemezsiniz.', 'danger')
        return redirect(url_for('admin.user_management'))

    db = g.db
    db.execute('DELETE FROM kullanicilar WHERE id = ?', (user_id,))
    db.commit()
    flash('Kullanıcı hesabı başarıyla silindi. Personel kaydı silinmedi.', 'success')
    return redirect(url_for('admin.user_management'))

@bp.route('/users/generate_password/<int:user_id>', methods=('POST',))
@admin_required
def generate_new_password(user_id):
    db = g.db
    user = db.execute("SELECT * FROM kullanicilar WHERE id = ?", (user_id,)).fetchone()
    if not user:
        flash("Kullanıcı bulunamadı.", "danger")
        return redirect(url_for('admin.user_management'))

    personnel = db.execute("SELECT * FROM calisanlar WHERE id = ?", (user['calisan_id'],)).fetchone()
    if not personnel:
        flash("Kullanıcıya bağlı personel kaydı bulunamadı.", "danger")
        return redirect(url_for('admin.edit_user', user_id=user_id))

    new_password = generate_random_password()
    hashed_password = generate_password_hash(new_password)

    db.execute("UPDATE kullanicilar SET password = ? WHERE id = ?", (hashed_password, user_id))
    db.commit()

    email_sent = False
    if personnel['mail']:
        email_sent = send_password_email(personnel['mail'], new_password)

    return render_template('show_password.html', 
                           personnel_name=personnel['ad_soyad'], 
                           new_password=new_password, 
                           email_sent=email_sent,
                           user_id=user_id)

@bp.route('/password_requests')
@admin_required
def password_requests():
    db = g.db
    requests = db.execute("SELECT sst.id, sst.talep_tarihi, c.ad_soyad, c.sicil_no, c.tc_kimlik FROM sifre_sifirlama_talepleri sst JOIN calisanlar c ON sst.calisan_id = c.id WHERE sst.durum = 'Beklemede' ORDER BY sst.talep_tarihi DESC").fetchall()
    return render_template('password_requests.html', requests=requests)

@bp.route('/reset_password/<int:request_id>', methods=('POST',))
@admin_required
def reset_password(request_id):
    db = g.db
    req = db.execute("SELECT * FROM sifre_sifirlama_talepleri WHERE id = ?", (request_id,)).fetchone()

    if not req:
        flash("Geçersiz şifre sıfırlama talebi.", "danger")
        return redirect(url_for('admin.password_requests'))

    personnel = db.execute("SELECT * FROM calisanlar WHERE id = ?", (req['calisan_id'],)).fetchone()
    if not personnel or not personnel['mail']:
        flash("Personelin sistemde kayıtlı bir e-posta adresi bulunamadığı için işlem yapılamıyor.", "danger")
        return redirect(url_for('admin.password_requests'))

    new_password = generate_random_password()
    hashed_password = generate_password_hash(new_password)

    db.execute("UPDATE kullanicilar SET password = ? WHERE calisan_id = ?", (hashed_password, req['calisan_id']))
    db.execute("UPDATE sifre_sifirlama_talepleri SET durum = 'Tamamlandı' WHERE id = ?", (request_id,))
    db.commit()

    if send_password_email(personnel['mail'], new_password):
        flash(f"{personnel['ad_soyad']} adlı personelin şifresi başarıyla sıfırlandı ve e-posta ile gönderildi.", "success")
    else:
        flash(f"Şifre başarıyla sıfırlandı ancak e-posta gönderilirken bir hata oluştu. Lütfen şifreyi ({new_password}) personele manuel olarak iletin.", "warning")

    return redirect(url_for('admin.password_requests'))

# --- YENİ ONAY MEKANİZMASI FONKSİYONLARI ---
@bp.route('/approvals')
@admin_required
def approval_list():
    """Onay bekleyen personelleri listeler."""
    db = g.db
    personnel = db.execute(
        "SELECT id, ad_soyad, tc_kimlik, ise_baslama_tarihi FROM calisanlar WHERE onay_durumu = 'Onay Bekliyor' ORDER BY id DESC"
    ).fetchall()
    return render_template('approval_list.html', personnel=personnel)

@bp.route('/approvals/process/<int:personnel_id>', methods=['POST'])
@admin_required
def process_approval(personnel_id):
    """Personel kaydını onaylama veya reddetme işlemini yapar."""
    action = request.form.get('action')
    db = g.db
    personnel = db.execute("SELECT * FROM calisanlar WHERE id = ? AND onay_durumu = 'Onay Bekliyor'", (personnel_id,)).fetchone()

    if not personnel:
        flash("İşlem yapılacak personel bulunamadı.", "danger")
        return redirect(url_for('admin.approval_list'))

    if action == 'approve':
        db.execute("UPDATE calisanlar SET onay_durumu = 'Onaylandı' WHERE id = ?", (personnel_id,))
        default_password = generate_random_password(8)
        hashed_password = generate_password_hash(default_password)
        db.execute("INSERT INTO kullanicilar (password, role, calisan_id) VALUES (?, ?, ?)", (hashed_password, 'user', personnel_id))
        flash(f"{personnel['ad_soyad']} adlı personel onaylandı ve kullanıcı hesabı oluşturuldu. Şifre: {default_password}", "success")

    elif action == 'reject':
        db.execute("DELETE FROM calisanlar WHERE id = ?", (personnel_id,))
        flash(f"{personnel['ad_soyad']} adlı personelin kaydı reddedildi ve silindi.", "info")

    db.commit()
    return redirect(url_for('admin.approval_list'))