import pytest
from app.database import get_db

def test_user_can_create_leave_request(client, auth, app):
    auth.login(tc_kimlik="22222222222", password="password123")
    with client:
        response = client.post("/leave/", data={
            "izin_tipi": "Yıllık İzin", "baslangic_tarihi": "2025-08-10",
            "bitis_tarihi": "2025-08-15", "aciklama": "Yaz tatili için."
        }, follow_redirects=True)
        assert response.status_code == 200
        assert "İzin talebiniz başarıyla alınmıştır.".encode("utf-8") in response.data

def test_admin_can_approve_leave_request(client, auth, app):
    auth.login()
    with client:
        # Bu test için özel bir talep oluşturalım
        with app.app_context():
             db = get_db()
             cursor = db.execute(
                "INSERT INTO izin_talepleri (calisan_id, izin_tipi, baslangic_tarihi, bitis_tarihi, durum) VALUES (?, ?, ?, ?, ?)",
                (2, 'Mazeret İzni', '2025-09-01', '2025-09-01', 'Beklemede')
             )
             request_id = cursor.lastrowid # Oluşturulan talebin ID'sini al
             db.commit()

        # Aldığımız ID'yi kullanarak talebi onayla
        response = client.post(f"/leave/action/{request_id}/approve", follow_redirects=True)
        assert response.status_code == 200
        assert "İzin talebi onaylandı.".encode("utf-8") in response.data

def test_admin_can_reject_leave_request(client, auth, app):
    auth.login()
    with client:
        # Bu test için de ayrı, özel bir talep oluşturalım
        with app.app_context():
             db = get_db()
             cursor = db.execute(
                "INSERT INTO izin_talepleri (calisan_id, izin_tipi, baslangic_tarihi, bitis_tarihi, durum) VALUES (?, ?, ?, ?, ?)",
                (2, 'Raporlu İzin', '2025-10-05', '2025-10-06', 'Beklemede')
             )
             request_id = cursor.lastrowid # Oluşturulan talebin ID'sini al
             db.commit()

        # Aldığımız ID'yi kullanarak talebi reddet
        response = client.post(f"/leave/action/{request_id}/reject", follow_redirects=True)
        assert response.status_code == 200
        assert "İzin talebi reddedildi.".encode("utf-8") in response.data