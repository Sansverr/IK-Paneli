import os
import click
from flask import Flask
from flask.cli import with_appcontext
from flask_login import LoginManager
from .database import db, User

def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)

    # Yapılandırmayı config.py dosyasından yükle
    app.config.from_object('config.Config')

    # Veritabanını uygulama ile başlat
    db.init_app(app)

    # LoginManager'ı başlat
    login_manager = LoginManager()
    login_manager.login_view = 'auth.login'
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # --- YENİ: Veritabanı oluşturma komutunu ekle ---
    @click.command('init-db')
    @with_appcontext
    def init_db_command():
        """Veritabanı tablolarını temizler ve yeniden oluşturur."""
        db.create_all()
        click.echo('Veritabanı başarıyla başlatıldı.')

    app.cli.add_command(init_db_command)
    # --- YENİ KOD SONU ---

    # Blueprint'leri kaydet
    from . import auth, personnel, leave, admin, dashboard, performance, data_management
    app.register_blueprint(auth.bp)
    app.register_blueprint(personnel.bp)
    app.register_blueprint(leave.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(dashboard.bp)
    app.register_blueprint(performance.bp)
    app.register_blueprint(data_management.bp)

    return app
