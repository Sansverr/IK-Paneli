# app/__init__.py

import os
import sqlite3
from flask import Flask, g, session

def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)

    app.config.from_object('config.Config')

    if test_config is not None:
        app.config.from_mapping(test_config)

    from . import database
    with app.app_context():
        database.init_db()

    @app.before_request
    def before_request():
        g.db = sqlite3.connect(app.config['DATABASE'])
        g.db.row_factory = sqlite3.Row

        # Admin için onay bekleyen sayısını yükle
        if session.get('role') == 'admin':
            count = g.db.execute("SELECT COUNT(id) FROM calisanlar WHERE onay_durumu = 'Onay Bekliyor'").fetchone()[0]
            g.pending_approvals = count
        else:
            g.pending_approvals = 0

    @app.teardown_request
    def teardown_request(exception):
        db = getattr(g, 'db', None)
        if db is not None:
            db.close()

    # --- DÜZELTME BURADA ---
    from . import auth, dashboard, personnel, leave, performance, admin, data_management

    app.register_blueprint(auth.bp)
    app.register_blueprint(dashboard.bp)
    app.register_blueprint(personnel.bp)
    app.register_blueprint(leave.bp)
    app.register_blueprint(performance.bp)
    app.register_blueprint(admin.bp)
    # --- EKSİK SATIR BURAYA EKLENDİ ---
    app.register_blueprint(data_management.bp)

    app.add_url_rule('/', endpoint='dashboard.index')

    return app