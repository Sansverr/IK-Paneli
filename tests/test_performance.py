import pytest
from app.database import get_db

def test_performance_management_requires_admin_role(client, auth):
    auth.login(tc_kimlik="22222222222", password="password123")
    with client:
        response = client.get("/performance/", follow_redirects=True)
        assert "Bu sayfaya erişim yetkiniz bulunmamaktadır.".encode("utf-8") in response.data

def test_admin_can_create_performance_period(client, auth, app):
    auth.login()
    with client:
        response = client.post(
            "/performance/",
            data={
                "donem_adi": "2025 Yıl Sonu Değerlendirmesi",
                "baslangic_tarihi": "2025-12-01",
                "bitis_tarihi": "2025-12-31"
            },
            follow_redirects=True
        )
        assert response.status_code == 200
        # DÜZELTME: Doğru flash mesajını arıyoruz
        assert "değerlendirme dönemi başarıyla oluşturuldu.".encode("utf-8") in response.data

def test_admin_can_assign_target_to_employee(client, auth, app):
    auth.login()
    with client:
        with app.app_context():
            db = get_db()
            db.execute("INSERT INTO degerlendirme_donemleri (donem_adi) VALUES (?)", ("Test Dönemi",))
            db.commit()

        response = client.post(
            "/performance/period/1",
            data={
                "calisan_id": 2,
                "hedef_aciklamasi": "Yeni müşteri kazanım oranını %10 artırmak.",
                "agirlik": 100
            },
            follow_redirects=True
        )
        assert response.status_code == 200
        # DÜZELTME: Doğru flash mesajını arıyoruz
        assert "Yeni hedef başarıyla eklendi.".encode("utf-8") in response.data