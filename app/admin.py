# app/admin.py

from flask import (
    Blueprint, flash, redirect, render_template, request, url_for
)
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash

# Yeni SQLAlchemy yapısı için gerekli importlar
from .database import db, User, PasswordResetRequest, Personnel
from .auth import admin_required
# utils.py dosyasındaki fonksiyonları kullanacağız
from .utils import generate_random_password, send_password_email

bp = Blueprint('admin', __name__, url_prefix='/admin')

@bp.route('/users')
@admin_required
def user_management():
    """Kullanıcı yönetimi sayfasını oluşturur."""
    try:
        requests_count = PasswordResetRequest.query.filter_by(status='pending').count()
        # Hesabı olan kullanıcıları personel bilgileriyle birlikte listele
        users = User.query.all()
        # Henüz kullanıcı hesabı oluşturulmamış personeli listele
        unlinked_personnel = Personnel.query.filter(Personnel.users == None, Personnel.onay_durumu == 'Onaylandı').all()
    except Exception as e:
        flash(f"Veriler yüklenirken bir hata oluştu: {e}", "danger")
        users, requests_count, unlinked_personnel = [], 0, []

    return render_template('user_management.html', users=users, password_requests_count=requests_count, unlinked_personnel=unlinked_personnel)

@bp.route('/users/add', methods=('POST',))
@admin_required
def add_user():
    """Mevcut bir personele yeni kullanıcı hesabı ekler."""
    personnel_id = request.form.get('personnel_id')
    role = request.form.get('role', 'user')

    if not personnel_id:
        flash("Lütfen bir personel seçin.", "danger")
        return redirect(url_for('admin.user_management'))

    personnel = Personnel.query.get(personnel_id)
    if not personnel or personnel.users:
        flash("Seçilen personel için zaten bir kullanıcı hesabı mevcut veya personel bulunamadı.", "warning")
        return redirect(url_for('admin.user_management'))

    try:
        default_password = generate_random_password(8)
        new_user = User(
            username=personnel.tc_kimlik_no,
            role=role
        )
        new_user.set_password(default_password)
        new_user.personnel.append(personnel)

        db.session.add(new_user)
        db.session.commit()
        flash(f"Personele başarıyla kullanıcı hesabı oluşturuldu. İletilmesi gereken şifre: {default_password}", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Kullanıcı oluşturulurken bir hata oluştu: {e}", "danger")

    return redirect(url_for('admin.user_management'))

@bp.route('/users/edit/<int:user_id>', methods=('GET', 'POST'))
@admin_required
def edit_user(user_id):
    """Bir kullanıcının rolünü düzenler."""
    user = User.query.get_or_404(user_id)
    if request.method == 'POST':
        new_role = request.form.get('role')
        if user.id == current_user.id and new_role != current_user.role:
            flash('Kendi yetkinizi değiştiremezsiniz.', 'danger')
        else:
            user.role = new_role
            db.session.commit()
            flash(f"Kullanıcının yetkisi '{new_role}' olarak güncellendi.", "success")
        return redirect(url_for('admin.user_management'))
    return render_template('edit_user.html', user=user)

@bp.route('/users/delete/<int:user_id>', methods=('POST',))
@admin_required
def delete_user(user_id):
    """Bir kullanıcı hesabını siler (personel kaydı kalır)."""
    if user_id == current_user.id:
        flash('Kendi hesabınızı silemezsiniz.', 'danger')
        return redirect(url_for('admin.user_management'))

    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    flash('Kullanıcı hesabı başarıyla silindi. Personel kaydı etkilenmedi.', 'success')
    return redirect(url_for('admin.user_management'))

@bp.route('/password_requests')
@admin_required
def password_requests():
    """Bekleyen şifre sıfırlama taleplerini listeler."""
    requests = PasswordResetRequest.query.filter_by(status='pending').order_by(PasswordResetRequest.id.desc()).all()
    return render_template('password_requests.html', requests=requests)

@bp.route('/reset_password/<int:request_id>', methods=('POST',))
@admin_required
def reset_password(request_id):
    """Bir şifre talebini onaylar ve yeni şifre atar."""
    req = PasswordResetRequest.query.get_or_404(request_id)
    user = req.user
    personnel = user.personnel[0] if user.personnel else None

    if not personnel or not personnel.email:
        flash("Personelin sistemde kayıtlı bir e-posta adresi bulunamadı.", "danger")
        return redirect(url_for('admin.password_requests'))

    try:
        new_password = generate_random_password()
        user.set_password(new_password)
        req.status = 'Tamamlandı'
        db.session.commit()

        if send_password_email(personnel.email, new_password):
            flash(f"{personnel.name} adlı personelin şifresi sıfırlandı ve e-posta ile gönderildi.", "success")
        else:
            flash(f"Şifre sıfırlandı ancak e-posta gönderilemedi. Lütfen şifreyi ({new_password}) personele manuel iletin.", "warning")
    except Exception as e:
        db.session.rollback()
        flash(f"İşlem sırasında bir hata oluştu: {e}", "danger")

    return redirect(url_for('admin.password_requests'))

@bp.route('/approvals')
@admin_required
def approval_list():
    """Onay bekleyen personel kayıtlarını listeler."""
    personnel_to_approve = Personnel.query.filter_by(onay_durumu='Onay Bekliyor').order_by(Personnel.id.desc()).all()
    return render_template('approval_list.html', personnel=personnel_to_approve)

@bp.route('/approvals/process/<int:personnel_id>', methods=['POST'])
@admin_required
def process_approval(personnel_id):
    """Bir personel kaydını onaylar veya reddeder."""
    personnel = Personnel.query.get_or_404(personnel_id)
    action = request.form.get('action')

    try:
        if action == 'approve':
            personnel.onay_durumu = 'Onaylandı'

            # Personel için yeni bir kullanıcı hesabı oluştur
            default_password = generate_random_password(8)
            new_user = User(username=personnel.tc_kimlik_no, role='user')
            new_user.set_password(default_password)
            new_user.personnel.append(personnel)

            db.session.add(new_user)
            db.session.commit()
            flash(f"{personnel.name} adlı personel onaylandı. Geçici şifre: {default_password}", "success")

        elif action == 'reject':
            db.session.delete(personnel)
            db.session.commit()
            flash(f"{personnel.name} adlı personelin kaydı reddedildi ve silindi.", "info")

    except Exception as e:
        db.session.rollback()
        flash(f"İşlem sırasında bir hata oluştu: {e}", "danger")

    return redirect(url_for('admin.approval_list'))
