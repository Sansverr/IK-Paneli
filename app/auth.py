# app/auth.py

import functools
from flask import (
    Blueprint, flash, redirect, render_template, request, url_for
)
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash

# Yeni SQLAlchemy yapısı için gerekli importlar
# PasswordResetRequest modeli eklendi
from .database import db, User, PasswordResetRequest

bp = Blueprint('auth', __name__, url_prefix='/auth')


# --- YENİ: Rol ve Yetki Kontrol Fonksiyonları ---

def role_required(role):
    """Belirli bir role sahip kullanıcıların erişebileceği sayfalar için decorator."""
    def decorator(f):
        @functools.wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or current_user.role != role:
                flash("Bu sayfaya erişim yetkiniz yok.", "warning")
                return redirect(url_for('dashboard.index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

admin_required = role_required('admin')

def personnel_linked_required(f):
    """Kullanıcının bir personel kaydına bağlı olmasını gerektiren decorator."""
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.role == 'admin':
            return f(*args, **kwargs)
        if not current_user.personnel:
            return redirect(url_for('auth.unlinked_user'))
        return f(*args, **kwargs)
    return decorated_function

@bp.route('/unlinked')
@login_required
def unlinked_user():
    """Personel kaydı olmayan kullanıcılar için gösterilecek sayfa."""
    return render_template('unlinked_user.html')


# --- MEVCUT GİRİŞ VE ÇIKIŞ FONKSİYONLARI ---

@bp.route('/login', methods=('GET', 'POST'))
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        tc_kimlik = request.form['tc_kimlik']
        password = request.form['password']
        error = None

        user = User.query.filter_by(username=tc_kimlik).first()

        if user is None:
            error = 'Geçersiz TC Kimlik Numarası.'
        elif not user.check_password(password):
            error = 'Hatalı şifre.'

        if error is None:
            login_user(user)
            return redirect(url_for('dashboard.index'))

        flash(error)

    return render_template('login.html')

@bp.route('/logout')
@login_required
def logout():
    """Kullanıcıyı sistemden çıkarır."""
    logout_user()
    return redirect(url_for('auth.login'))

# --- YENİ: Şifremi Unuttum Fonksiyonu ---
@bp.route('/forgot_password', methods=('GET', 'POST'))
def forgot_password():
    """Kullanıcıların şifre sıfırlama talebi oluşturmasını sağlar."""
    if request.method == 'POST':
        tc_kimlik = request.form['tc_kimlik']
        user = User.query.filter_by(username=tc_kimlik).first()

        if user:
            # Mevcut bir talep var mı kontrol et
            existing_request = PasswordResetRequest.query.filter_by(user_id=user.id, status='pending').first()
            if existing_request:
                flash('Zaten beklemede olan bir şifre sıfırlama talebiniz var.', 'warning')
            else:
                # Yeni bir şifre sıfırlama talebi oluştur
                # Not: Bu basit implementasyonda yeni şifre admin tarafından atanmalıdır.
                reset_request = PasswordResetRequest(user_id=user.id, new_password='-') 
                db.session.add(reset_request)
                db.session.commit()
                flash('Şifre sıfırlama talebiniz yöneticiye iletilmiştir.', 'success')
            return redirect(url_for('auth.login'))
        else:
            flash('Bu TC Kimlik Numarasına sahip bir kullanıcı bulunamadı.', 'danger')

    return render_template('forgot_password.html')
