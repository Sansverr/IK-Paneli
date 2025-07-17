# app/utils.py

import random
import string
import smtplib
from email.mime.text import MIMEText
from flask import current_app

def generate_random_password(length=10):
    """Belirtilen uzunlukta rastgele bir şifre oluşturur."""
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for i in range(length))

def send_password_email(recipient_email, new_password):
    """Yeni şifreyi personele e-posta ile gönderir."""
    # E-posta ayarlarının config.py veya ortam değişkenlerinde tam olması gerekir.
    conf = current_app.config
    if not all([conf.get('SMTP_SERVER'), conf.get('SMTP_PORT'), conf.get('SMTP_USERNAME'), conf.get('SMTP_PASSWORD'), conf.get('SENDER_EMAIL')]):
        print("UYARI: E-posta (SMTP) ayarları tam olarak yapılandırılmamış. E-posta gönderilemedi.")
        return False

    try:
        msg_body = f"Sayın personelimiz,\n\nİK Paneli için yeni şifreniz aşağıda belirtilmiştir.\n\nYeni Şifreniz: {new_password}\n\nİyi çalışmalar dileriz."
        msg = MIMEText(msg_body, "plain", "utf-8")
        msg['Subject'] = 'İK Paneli Yeni Şifre Bilgilendirmesi'
        msg['From'] = conf['SENDER_EMAIL']
        msg['To'] = recipient_email

        with smtplib.SMTP(conf['SMTP_SERVER'], conf['SMTP_PORT']) as server:
            server.starttls()
            server.login(conf['SMTP_USERNAME'], conf['SMTP_PASSWORD'])
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"E-posta gönderim hatası: {e}")
        return False