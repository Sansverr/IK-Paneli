# app/__init__.py

import os
import click
from flask import Flask, g
from flask.cli import with_appcontext
from flask_login import LoginManager, current_user

# Gerekli tüm modelleri ve sabitleri import et
from .database import db, User, Personnel, EvrakTipi, GEREKLI_OZLUK_EVRAKLARI, GEREKLI_ISE_BASLANGIC_SURECLERI

def create_app(test_config=None):
    """Uygulama fabrikası: Flask uygulamasını oluşturur ve yapılandırır."""
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object('config.Config')

    # Dosya yükleme klasörünü kontrol et ve oluştur
    try:
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    except OSError as e:
        app.logger.error(f"Upload klasörü oluşturulurken hata oluştu: {e}")

    # SQLAlchemy ve Flask-Login eklentilerini başlat
    db.init_app(app)
    login_manager = LoginManager()
    login_manager.login_view = 'auth.login' # Giriş yapılmamışsa yönlendirilecek sayfa
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        """Flask-Login için kullanıcı yükleyici fonksiyonu."""
        return User.query.get(int(user_id))

    # --- Orijinal Mantık (SQLAlchemy ile Güncellendi) ---
    @app.before_request
    def before_request():
        """Her istekten önce çalışır ve onay bekleyen personel sayısını yükler."""
        g.pending_approvals = 0
        # Sadece giriş yapmış ve rolü admin olan kullanıcılar için sayıyı hesapla
        if current_user.is_authenticated and current_user.role == 'admin':
            g.pending_approvals = Personnel.query.filter_by(onay_durumu='Onay Bekliyor').count()

    # --- Veritabanı Sıfırlama Komutu (Güncel) ---
    @click.command('init-db')
    @with_appcontext
    def init_db_command():
        """Mevcut veritabanını sıfırlar, yeniden oluşturur ve varsayılan verileri ekler."""
        click.echo('Eski tablolar siliniyor...')
        db.drop_all()
        click.echo('Yeni tablolar oluşturuluyor...')
        db.create_all()
        click.echo('Varsayılan evrak tipleri ekleniyor...')
        try:
            for evrak in GEREKLI_OZLUK_EVRAKLARI: db.session.add(EvrakTipi(evrak_adi=evrak, kategori='Özlük'))
            for surec in GEREKLI_ISE_BASLANGIC_SURECLERI: db.session.add(EvrakTipi(evrak_adi=surec, kategori='İşe Başlangıç'))
            db.session.commit()
            click.echo('Evrak tipleri başarıyla eklendi.')
        except Exception as e:
            db.session.rollback()
            click.echo(f'Evrak tipleri eklenirken hata oluştu: {e}')
        click.echo('Veritabanı başarıyla sıfırlandı ve yeniden başlatıldı.')

    app.cli.add_command(init_db_command)

    # --- Blueprint'leri Kaydet ---
    from . import auth, dashboard, personnel, leave, performance, admin, data_management
    app.register_blueprint(auth.bp)
    app.register_blueprint(dashboard.bp)
    app.register_blueprint(personnel.bp)
    app.register_blueprint(leave.bp)
    app.register_blueprint(performance.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(data_management.bp)

    # --- Orijinal Mantık: Ana sayfa yönlendirmesi ---
    app.add_url_rule('/', endpoint='dashboard.index')

    return app
