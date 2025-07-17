from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for
)
from werkzeug.security import check_password_hash
from datetime import datetime
from functools import wraps

# Blueprint'i oluştur
bp = Blueprint('auth', __name__, url_prefix='/auth')

# --- YETKİ KONTROL DECORATOR'LARI ---
# Bu fonksiyonlar artık diğer modüller tarafından "from .auth import login_required" şeklinde çağrılacak.
def login_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        if 'user_id' not in session:
            flash("Bu sayfayı görüntülemek için lütfen giriş yapın.", "warning")
            return redirect(url_for('auth.login'))
        return view(**kwargs)
    return wrapped_view

def admin_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        if session.get('role') != 'admin':
            flash("Bu sayfaya erişim yetkiniz bulunmamaktadır.", "danger")
            return redirect(url_for('dashboard.index'))
        return view(**kwargs)
    return wrapped_view

def personnel_linked_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        if "calisan_id" not in session or session["calisan_id"] is None:
            return render_template('unlinked_user.html')
        return view(**kwargs)
    return wrapped_view

# --- ROTALAR ---
@bp.route('/login', methods=('GET', 'POST'))
def login():
    # Login fonksiyonu içeriği aynı kalabilir...
    if 'user_id' in session:
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        tc_kimlik = request.form.get('tc_kimlik')
        password = request.form.get('password')
        db = g.db
        error = None

        personnel = db.execute(
            'SELECT * FROM calisanlar WHERE tc_kimlik = ? AND onay_durumu = "Onaylandı"', (tc_kimlik,)
        ).fetchone()

        if personnel is None:
            error = "Geçersiz TC Kimlik Numarası veya hesap onaylanmamış."
        else:
            user = db.execute('SELECT * FROM kullanicilar WHERE calisan_id = ?', (personnel['id'],)).fetchone()
            if user is None or not check_password_hash(user['password'], password):
                error = 'Geçersiz şifre.'
            else:
                session.clear()
                session['user_id'] = user['id']
                session['role'] = user['role']
                session['calisan_id'] = user['calisan_id']
                session['ad_soyad'] = personnel['ad_soyad']
                return redirect(url_for('dashboard.index'))

        flash(error, "danger")

    return render_template('login.html')

@bp.route('/logout')
def logout():
    session.clear()
    flash("Başarıyla çıkış yaptınız.", "info")
    return redirect(url_for('auth.login'))

@bp.route('/forgot_password', methods=('GET', 'POST'))
def forgot_password():
    # Bu fonksiyonun içeriği de aynı kalabilir...
    if request.method == 'POST':
        tc_kimlik = request.form.get('tc_kimlik')
        db = g.db
        personnel = db.execute('SELECT id FROM calisanlar WHERE tc_kimlik = ?', (tc_kimlik,)).fetchone()

        if personnel:
            existing_request = db.execute("SELECT id FROM sifre_sifirlama_talepleri WHERE calisan_id = ? AND durum = 'Beklemede'", (personnel['id'],)).fetchone()
            if existing_request:
                flash("Bu personel için zaten beklemede olan bir şifre sıfırlama talebi mevcut.", "warning")
            else:
                db.execute("INSERT INTO sifre_sifirlama_talepleri (calisan_id, talep_tarihi) VALUES (?, ?)", (personnel['id'], datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                db.commit()
                flash("Şifre sıfırlama talebiniz sistem yöneticisine iletilmiştir.", "success")
        else:
            flash("Bu TC Kimlik Numarasına sahip bir personel bulunamadı.", "danger")

        return redirect(url_for('auth.login'))
    return render_template('forgot_password.html')