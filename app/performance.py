from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for
)
from app.auth import login_required, admin_required, personnel_linked_required

bp = Blueprint('performance', __name__, url_prefix='/performance')

@bp.route('/', methods=('GET', 'POST'))
@admin_required
def management():
    db = g.db
    if request.method == 'POST':
        donem_adi = request.form.get('donem_adi')
        baslangic_tarihi = request.form.get('baslangic_tarihi')
        bitis_tarihi = request.form.get('bitis_tarihi')
        if not donem_adi or not baslangic_tarihi or not bitis_tarihi:
            flash("Tüm alanlar zorunludur.", "danger")
        else:
            db.execute("INSERT INTO degerlendirme_donemleri (donem_adi, baslangic_tarihi, bitis_tarihi) VALUES (?, ?, ?)",
                       (donem_adi, baslangic_tarihi, bitis_tarihi))
            db.commit()
            flash(f"'{donem_adi}' adlı değerlendirme dönemi başarıyla oluşturuldu.", "success")
        return redirect(url_for('performance.management'))

    periods = db.execute("SELECT * FROM degerlendirme_donemleri ORDER BY baslangic_tarihi DESC").fetchall()
    return render_template('performance_management.html', periods=periods)

@bp.route('/period/<int:period_id>', methods=('GET', 'POST'))
@personnel_linked_required
def period_detail(period_id):
    if session.get('role') not in ['admin', 'manager']:
        flash("Bu sayfaya erişim yetkiniz yok.", "danger")
        return redirect(url_for('dashboard.index'))

    db = g.db
    period = db.execute('SELECT * FROM degerlendirme_donemleri WHERE id = ?', (period_id,)).fetchone()
    if not period:
        flash("Dönem bulunamadı", "danger")
        return redirect(url_for('performance.management'))

    if request.method == 'POST':
        calisan_id = request.form.get('calisan_id')
        hedef_aciklamasi = request.form.get('hedef_aciklamasi')
        agirlik = request.form.get('agirlik', 100)

        if not calisan_id or not hedef_aciklamasi:
            flash("Personel ve Hedef Açıklaması alanları zorunludur.", "danger")
        else:
            db.execute("INSERT INTO personel_hedefleri (calisan_id, donem_id, hedef_aciklamasi, agirlik) VALUES (?, ?, ?, ?)",
                       (calisan_id, period_id, hedef_aciklamasi, agirlik))
            db.commit()
            flash("Yeni hedef başarıyla eklendi.", "success")
        return redirect(url_for('performance.period_detail', period_id=period_id))

    employees_to_manage = []
    if session.get('role') == 'admin':
        employees_to_manage = db.execute("SELECT id, ad_soyad, sicil_no FROM calisanlar WHERE isten_cikis_tarihi IS NULL OR isten_cikis_tarihi = '' ORDER BY ad_soyad").fetchall()
    elif session.get('role') == 'manager':
        employees_to_manage = db.execute("SELECT id, ad_soyad, sicil_no FROM calisanlar WHERE (isten_cikis_tarihi IS NULL OR isten_cikis_tarihi = '') AND yonetici_id = ? ORDER BY ad_soyad", (session.get('calisan_id'),)).fetchall()

    targets = db.execute("SELECT ph.*, c.ad_soyad FROM personel_hedefleri ph JOIN calisanlar c ON ph.calisan_id = c.id WHERE ph.donem_id = ? ORDER BY c.ad_soyad", (period_id,)).fetchall()

    return render_template('performance_period_detail.html', period=period, employees=employees_to_manage, targets=targets)

@bp.route('/target/delete/<int:target_id>', methods=['POST'])
@login_required
def delete_target(target_id):
    if session.get('role') not in ['admin', 'manager']:
        flash("Bu işlemi yapma yetkiniz yok.", "danger")
        return redirect(url_for('dashboard.index'))

    db = g.db
    target = db.execute("SELECT * FROM personel_hedefleri WHERE id = ?", (target_id,)).fetchone()
    if not target:
        flash("Silinecek hedef bulunamadı.", "danger")
        return redirect(url_for('performance.management'))

    period_id = target['donem_id']
    db.execute("DELETE FROM personel_hedefleri WHERE id = ?", (target_id,))
    db.commit()
    flash("Hedef başarıyla silindi.", "success")
    return redirect(url_for('performance.period_detail', period_id=period_id))