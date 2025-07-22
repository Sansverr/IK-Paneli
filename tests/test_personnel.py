import pytest
from app.database import get_db
from datetime import date, timedelta

# Bu fikstür, bu dosyadaki her testten önce otomatik olarak admin olarak giriş yapar.
@pytest.fixture(autouse=True)
def admin_login(auth):
    auth.login()

# --- Personel Ekleme Testleri ---

def test_add_personnel_with_all_required_fields_is_successful(client):
    birth_date = (date.today() - timedelta(days=20*365)).strftime('%Y-%m-%d')
    with client:
        response = client.post("/personnel/add", data={
            "ad": "Başarılı", "soyad": "Kayıt", "tc_kimlik": "10101010101",
            "sicil_no": "98765", "ise_baslama_tarihi": "2025-01-01",
            "mail": "basarili@kayit.com", "dogum_tarihi": birth_date,
            "cinsiyet": "Kadın", "kan_grubu": "A Rh+", "tel": "05551112233",
            "yakin_tel": "05554445566", "adres": "Test Adresi", "sube_id": "1",
            "departman_id": "1", "gorev_id": "1", "yaka_tipi": "BEYAZ YAKA", "egitim": "Lisans"
        }, follow_redirects=True)
        assert "Yeni personel kaydı başarıyla oluşturuldu.".encode("utf-8") in response.data

def test_add_personnel_under_16_is_rejected(client):
    birth_date = (date.today() - timedelta(days=15*365)).strftime('%Y-%m-%d')
    full_data = {
        "ad": "Onbeş", "soyad": "Yaşında", "tc_kimlik": "15151515151",
        "sicil_no": "15151", "ise_baslama_tarihi": "2025-01-01",
        "mail": "onbes@yasinda.com", "dogum_tarihi": birth_date,
        "cinsiyet": "Erkek", "kan_grubu": "0 Rh-", "tel": "05001515151",
        "yakin_tel": "05001515152", "adres": "Test Adresi 15", "sube_id": "1",
        "departman_id": "1", "gorev_id": "1", "yaka_tipi": "MAVI YAKA", "egitim": "Ortaokul"
    }
    with client:
        response = client.post("/personnel/add", data=full_data, follow_redirects=True)
        assert "Personel 16 yaşından küçük olamaz.".encode("utf-8") in response.data

def test_add_personnel_under_18_is_added_with_warning(client, app):
    birth_date = (date.today() - timedelta(days=17*365)).strftime('%Y-%m-%d')
    full_data = {
        "ad": "Genç", "soyad": "Personel", "tc_kimlik": "20202020202",
        "sicil_no": "12312", "ise_baslama_tarihi": "2025-01-01",
        "mail": "genc@personel.com", "dogum_tarihi": birth_date,
        "cinsiyet": "Erkek", "kan_grubu": "0 Rh+", "tel": "05441112233",
        "yakin_tel": "05334445566", "adres": "Test Adresi 2", "sube_id": "1",
        "departman_id": "1", "gorev_id": "1", "yaka_tipi": "MAVI YAKA", "egitim": "Lise"
    }
    with client:
        response = client.post("/personnel/add", data=full_data, follow_redirects=True)
        assert "Yeni personel kaydı başarıyla oluşturuldu.".encode("utf-8") in response.data
        assert "Uyarı: Eklenen personel 18 yaşından küçüktür.".encode("utf-8") in response.data

def test_add_personnel_with_missing_required_field_is_rejected(client):
    with client:
        response = client.post("/personnel/add", data={"ad": "Eksik"}, follow_redirects=True)
        assert "Lütfen IBAN ve Ücreti dışındaki tüm zorunlu alanları doldurun.".encode("utf-8") in response.data

def test_add_personnel_with_invalid_phone_format_is_rejected(client):
    full_data = { "ad": "Telefon", "soyad": "Hatalı", "tc_kimlik": "30303030303", "sicil_no": "54321", "ise_baslama_tarihi": "2025-01-01", "mail": "telefon@hatali.com", "dogum_tarihi": "2000-01-01", "cinsiyet": "Kadın", "kan_grubu": "A Rh+", "tel": "12345", "yakin_tel": "05554445566", "adres": "Test Adresi", "sube_id": "1", "departman_id": "1", "gorev_id": "1", "yaka_tipi": "BEYAZ YAKA", "egitim": "Lisans" }
    with client:
        response = client.post("/personnel/add", data=full_data, follow_redirects=True)
        assert "Telefon numarası 11 haneli bir sayı olmalıdır.".encode("utf-8") in response.data

# --- Personel Güncelleme Testleri ---

def test_admin_can_update_editable_fields(client, app):
    with client:
        with app.app_context():
            db = get_db()
            cursor = db.execute("INSERT INTO calisanlar (ad, soyad, tc_kimlik, sicil_no, onay_durumu, mail, adres, tel, yakin_tel, dogum_tarihi, cinsiyet, kan_grubu, ise_baslama_tarihi, sube_id, departman_id, gorev_id, yaka_tipi, egitim) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                ("Eski", "İsim", "55555555555", "98765", "Onaylandı", "eski@mail.com", "Eski Adres", "05550000000", "05551111111", "1990-01-01", "Erkek", "A Rh+", "2024-01-01", 1, 1, 1, "BEYAZ YAKA", "Lisans"))
            personnel_id = cursor.lastrowid
            db.commit()

        response = client.post(f"/personnel/update/{personnel_id}", data={
            'ad': 'Eski', 'soyad': 'İsim', 'tc_kimlik': '55555555555', 'sicil_no': '98765', 'ise_baslama_tarihi': '2024-01-01', 'dogum_tarihi': '1990-01-01',
            'mail': 'yeni@mail.com', 'adres': 'Yeni Adres', 'tel': '05559998877', 'yakin_tel': '05558887766',
            'cinsiyet': 'Erkek', 'kan_grubu': 'A Rh+', 'sube_id': '1', 'departman_id': '1', 'gorev_id': '1', 'yaka_tipi': 'BEYAZ YAKA', 'egitim': 'Lisans'
        }, follow_redirects=True)

        assert "Personel bilgileri başarıyla güncellendi.".encode("utf-8") in response.data

def test_update_locked_field_is_ignored(client, app):
    with client:
        with app.app_context():
            db = get_db()
            cursor = db.execute("INSERT INTO calisanlar (ad, soyad, tc_kimlik, sicil_no, onay_durumu) VALUES (?, ?, ?, ?, ?)",
                                ("Değişmez", "Soyad", "44444444444", "44444", "Onaylandı"))
            personnel_id = cursor.lastrowid
            db.commit()

        form_data = { 'ad': 'Değişti mi?', 'soyad': 'Soyad', 'tc_kimlik': '44444444444', 'sicil_no': '44444', 'ise_baslama_tarihi': '2024-01-01', 'dogum_tarihi': '1990-01-01', 'cinsiyet': 'Erkek', 'kan_grubu': 'A Rh+', 'tel': '05111111111', 'yakin_tel': '05222222222', 'adres': 'Adres', 'sube_id': '1', 'departman_id': '1', 'gorev_id': '1', 'yaka_tipi': 'BEYAZ YAKA', 'egitim': 'Lisans', 'mail': 'degismez@mail.com' }
        client.post(f"/personnel/update/{personnel_id}", data=form_data)

        with app.app_context():
            db = get_db()
            personnel = db.execute("SELECT ad FROM calisanlar WHERE id = ?", (personnel_id,)).fetchone()
            assert personnel['ad'] == 'Değişmez'

# --- Yetkilendirme Testleri ---

def test_user_cannot_access_add_personnel(client, auth):
    auth.logout()
    auth.login(tc_kimlik="22222222222", password="password123")
    with client:
        response = client.get("/personnel/add", follow_redirects=True)
        assert "Bu sayfaya erişim yetkiniz bulunmamaktadır.".encode("utf-8") in response.data

def test_admin_can_see_user_management(client):
     with client:
        response = client.get("/admin/users")
        assert "Kullanıcı Yönetimi".encode("utf-8") in response.data

def test_user_cannot_see_user_management(client, auth):
    auth.logout()
    auth.login(tc_kimlik="22222222222", password="password123")
    with client:
        response = client.get("/admin/users", follow_redirects=True)
        assert "Bu sayfaya erişim yetkiniz bulunmamaktadır.".encode("utf-8") in response.data