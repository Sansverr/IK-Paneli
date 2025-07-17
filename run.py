# app paketinden create_app fonksiyonunu import et
from app import create_app

# Uygulama fabrikasını çağırarak uygulamayı oluştur
app = create_app()

if __name__ == '__main__':
    # Geliştirme aşamasında hataları görmek için debug=True
    # Canlıya alırken bunu False yapmalısın.
    app.run(host='0.0.0.0', port=8080, debug=True)