# app/performance.py

from flask import (
    Blueprint, flash, redirect, render_template, request, url_for
)
from flask_login import login_required
from datetime import datetime

# Yeni SQLAlchemy yapısı için gerekli importlar
from .database import db, PerformancePeriod, PersonnelGoal, Personnel
from .auth import admin_required

bp = Blueprint('performance', __name__, url_prefix='/performance')

@bp.route('/')
@admin_required
def management():
    """Performans dönemlerini listeler."""
    try:
        periods = PerformancePeriod.query.order_by(PerformancePeriod.baslangic_tarihi.desc()).all()
    except Exception as e:
        flash(f"Performans dönemleri yüklenirken bir hata oluştu: {e}", "danger")
        periods = []
    return render_template('performance_management.html', periods=periods)

@bp.route('/period/add', methods=('POST',))
@admin_required
def add_period():
    """Yeni bir performans dönemi ekler."""
    try:
        donem_adi = request.form['donem_adi']
        baslangic_tarihi = datetime.strptime(request.form['baslangic_tarihi'], '%Y-%m-%d').date()
        bitis_tarihi = datetime.strptime(request.form['bitis_tarihi'], '%Y-%m-%d').date()

        new_period = PerformancePeriod(
            donem_adi=donem_adi,
            baslangic_tarihi=baslangic_tarihi,
            bitis_tarihi=bitis_tarihi
        )
        db.session.add(new_period)
        db.session.commit()
        flash(f"'{donem_adi}' dönemi başarıyla oluşturuldu.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Dönem oluşturulurken bir hata oluştu: {e}", "danger")

    return redirect(url_for('performance.management'))

@bp.route('/period/edit/<int:period_id>', methods=('POST',))
@admin_required
def edit_period(period_id):
    """Bir performans dönemini düzenler."""
    period = PerformancePeriod.query.get_or_404(period_id)
    try:
        period.donem_adi = request.form['donem_adi']
        period.baslangic_tarihi = datetime.strptime(request.form['baslangic_tarihi'], '%Y-%m-%d').date()
        period.bitis_tarihi = datetime.strptime(request.form['bitis_tarihi'], '%Y-%m-%d').date()
        period.durum = request.form['durum']
        db.session.commit()
        flash("Dönem başarıyla güncellendi.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Dönem güncellenirken bir hata oluştu: {e}", "danger")

    return redirect(url_for('performance.management'))

@bp.route('/period/delete/<int:period_id>', methods=('POST',))
@admin_required
def delete_period(period_id):
    """Bir performans dönemini ve ilişkili hedefleri siler."""
    period = PerformancePeriod.query.get_or_404(period_id)
    try:
        db.session.delete(period)
        db.session.commit()
        flash("Performans dönemi ve ilişkili tüm hedefler silindi.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Dönem silinirken bir hata oluştu: {e}", "danger")

    return redirect(url_for('performance.management'))

@bp.route('/period/<int:period_id>')
@admin_required
def period_detail(period_id):
    """Bir performans döneminin detaylarını ve personel hedeflerini gösterir."""
    period = PerformancePeriod.query.get_or_404(period_id)
    # Döneme ait hedefleri personel bilgileriyle birlikte getir
    goals = db.session.query(PersonnelGoal, Personnel).join(Personnel).filter(PersonnelGoal.donem_id == period_id).all()

    # Henüz hedef atanmamış personelleri bul
    personnel_with_goals_ids = [goal.calisan_id for goal, p in goals]
    personnel_without_goals = Personnel.query.filter(Personnel.id.notin_(personnel_with_goals_ids)).all()

    return render_template('performance_period_detail.html', period=period, goals=goals, personnel_without_goals=personnel_without_goals)

@bp.route('/goal/add/<int:period_id>/<int:calisan_id>', methods=('POST',))
@admin_required
def add_goal(period_id, calisan_id):
    """Bir personele yeni bir hedef ekler."""
    try:
        new_goal = PersonnelGoal(
            calisan_id=calisan_id,
            donem_id=period_id,
            hedef_aciklamasi=request.form['hedef_aciklamasi'],
            agirlik=request.form.get('agirlik', 100, type=int)
        )
        db.session.add(new_goal)
        db.session.commit()
        flash("Personele yeni hedef başarıyla eklendi.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Hedef eklenirken bir hata oluştu: {e}", "danger")

    return redirect(url_for('performance.period_detail', period_id=period_id))

@bp.route('/goal/delete/<int:goal_id>', methods=('POST',))
@admin_required
def delete_goal(goal_id):
    """Bir personel hedefini siler."""
    goal = PersonnelGoal.query.get_or_404(goal_id)
    period_id = goal.donem_id # Yönlendirme için dönemin ID'sini sakla
    try:
        db.session.delete(goal)
        db.session.commit()
        flash("Hedef başarıyla silindi.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Hedef silinirken bir hata oluştu: {e}", "danger")

    return redirect(url_for('performance.period_detail', period_id=period_id))
