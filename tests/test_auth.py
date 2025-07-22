# tests/test_auth.py
import pytest
from flask import session

def test_login_logout(client, auth):
    # Test için standart kullanıcılar conftest'te oluşturuldu.
    # Önce giriş yap
    response_login = auth.login(tc_kimlik="11111111111", password="password123")
    assert response_login.status_code == 302 # Başarılı giriş yönlendirme yapar

    # Giriş sonrası session kontrolü
    with client:
        client.get("/") # Session'ı güncellemek için bir istek at
        assert session.get("user_id") is not None
        assert session.get("ad_soyad") == "Admin User"

    # Sonra çıkış yap
    response_logout = auth.logout()
    assert response_logout.status_code == 302 # Başarılı çıkış da yönlendirme yapar

    # Çıkış sonrası session kontrolü
    with client:
        client.get("/")
        assert "user_id" not in session