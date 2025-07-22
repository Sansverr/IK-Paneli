import pytest
from app.database import get_db
import pandas as pd
from io import BytesIO

# Bu test, geçerli bir Excel dosyası ile hem yeni personel eklemeyi hem de mevcut olanı güncellemeyi doğrular.
def test_import_excel_with_valid_data(client, auth, app):
    auth.login() # Admin olarak giriş yap

    df = pd.DataFrame([
        {'TC Kimlik No': '11111111111', 'Adı': 'Admin', 'Soyadı': 'Kullanıcı Güncellendi'},
        {'TC Kimlik No': '88888888888', 'Adı': 'Yeni', 'Soyadı': 'Personel Excel'},
    ])
    output = BytesIO()
    df.to_excel(output, index=False, sheet_name='Personel Listesi')
    output.seek(0)

    with client:
        response = client.post(
            "/data_management/import",
            data={"excel_file": (output, 'test.xlsx')},
            content_type="multipart/form-data",
            follow_redirects=True
        )
        assert response.status_code == 200
        assert "1 yeni personel eklendi".encode("utf-8") in response.data
        assert "1 personel güncellendi".encode("utf-8") in response.data

# Bu test, hatalı ve doğru satırları içeren bir dosya yüklendiğinde,
# sistemin sadece doğruları işlediğini ve hatalıları atladığını doğrular.
def test_import_excel_skips_invalid_rows(client, auth, app):
    auth.login()

    df = pd.DataFrame([
        {'TC Kimlik No': '99999999999', 'Adı': 'Geçerli', 'Soyadı': 'Kayıt'},
        {'TC Kimlik No': '12345', 'Adı': 'Geçersiz TC', 'Soyadı': 'Kayıt'},
        {'TC Kimlik No': '88888888888', 'Adı': '', 'Soyadı': 'İsimsiz'},
    ])
    output = BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)

    with client:
        response = client.post(
            "/data_management/import",
            data={"excel_file": (output, 'test.xlsx')},
            follow_redirects=True
        )
        assert response.status_code == 200
        assert "1 yeni personel eklendi".encode("utf-8") in response.data
        assert "2 satır, geçersiz veya eksik TC/Ad/Soyad bilgisi nedeniyle atlandı.".encode("utf-8") in response.data

# YENİ TUTARLILIK TESTİ: Güncelleme işleminin mevcut verileri silmediğini doğrular.
def test_import_updates_only_provided_fields_for_consistency(client, auth, app):
    auth.login()

    # Adım 1: Test için sicil_no ve tel'i olan bir personel oluşturalım.
    with app.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO calisanlar (ad, soyad, tc_kimlik, sicil_no, tel, onay_durumu) VALUES (?, ?, ?, ?, ?, ?)",
            ("Ayşe", "Yılmaz", "55555555555", "AY2025", "05551234567", "Onaylandı")
        )
        db.commit()

    # Adım 2: Sadece soyadını ve adresini güncelleyen bir Excel dosyası oluşturalım.
    df = pd.DataFrame([
        {'TC Kimlik No': '55555555555', 'Soyadı': 'Çelik', 'Adres': 'Yeni Adres'},
    ])
    output = BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)

    with client:
        # Adım 3: Dosyayı yükleyelim.
        client.post(
            "/data_management/import",
            data={"excel_file": (output, 'test.xlsx')},
            follow_redirects=True
        )

    # Adım 4: Veritabanını kontrol edelim.
    with app.app_context():
        db = get_db()
        personnel = db.execute("SELECT * FROM calisanlar WHERE tc_kimlik = '55555555555'").fetchone()

        # Beklentiler:
        assert personnel['soyad'] == 'Çelik' # Bu güncellenmeli
        assert personnel['adres'] == 'Yeni Adres' # Bu güncellenmeli
        assert personnel['ad'] == 'Ayşe' # Bu DEĞİŞMEMELİ
        assert personnel['sicil_no'] == 'AY2025' # Bu DEĞİŞMEMELİ
        assert personnel['tel'] == '05551234567' # Bu DEĞİŞMEMELİ