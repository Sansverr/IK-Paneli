# tests/conftest.py

import os
import tempfile
import pytest
from app import create_app
from app.database import get_db, init_db
from werkzeug.security import generate_password_hash

@pytest.fixture
def app():
    db_fd, db_path = tempfile.mkstemp()
    app = create_app({
        'TESTING': True,
        'DATABASE': db_path,
        'SECRET_KEY': 'test', # Testler için flash mesajlarını kullanabilmek adına gerekli
    })

    with app.app_context():
        init_db()
        # Her test için standart kullanıcıları oluşturalım
        db = get_db()
        # Admin Kullanıcısı
        db.execute("INSERT INTO calisanlar (ad, soyad, tc_kimlik, onay_durumu) VALUES (?, ?, ?, ?)", ("Admin", "User", "11111111111", "Onaylandı"))
        admin_calisan_id = db.execute("SELECT id FROM calisanlar WHERE tc_kimlik = '11111111111'").fetchone()[0]
        db.execute("INSERT INTO kullanicilar (password, role, calisan_id) VALUES (?, ?, ?)", (generate_password_hash("password123"), "admin", admin_calisan_id))
        # Normal Kullanıcı
        db.execute("INSERT INTO calisanlar (ad, soyad, tc_kimlik, onay_durumu) VALUES (?, ?, ?, ?)", ("Normal", "User", "22222222222", "Onaylandı"))
        user_calisan_id = db.execute("SELECT id FROM calisanlar WHERE tc_kimlik = '22222222222'").fetchone()[0]
        db.execute("INSERT INTO kullanicilar (password, role, calisan_id) VALUES (?, ?, ?)", (generate_password_hash("password123"), "user", user_calisan_id))
        db.commit()

    yield app

    os.close(db_fd)
    os.unlink(db_path)

@pytest.fixture
def client(app):
    return app.test_client()

# Giriş yapma işlemini kolaylaştıran yardımcı
class AuthActions:
    def __init__(self, client):
        self._client = client

    def login(self, tc_kimlik="11111111111", password="password123"):
        return self._client.post(
            "/auth/login",
            data={"tc_kimlik": tc_kimlik, "password": password}
        )
    def logout(self):
        return self._client.get("/auth/logout")

@pytest.fixture
def auth(client):
    return AuthActions(client)