#!/usr/bin/env bash
# PrintForge AI - tek seferlik kurulum (macOS)
set -euo pipefail
cd "$(dirname "$0")"

echo "==> Gerekli araçlar kontrol ediliyor"
if ! command -v brew >/dev/null 2>&1; then
  echo "HATA: Homebrew bulunamadı. Önce https://brew.sh adresindeki tek satırlık komutla Homebrew'u kurun, sonra bu betiği tekrar çalıştırın."
  exit 1
fi
command -v uv  >/dev/null 2>&1 || { echo "==> uv (Python yöneticisi) kuruluyor"; brew install uv; }
command -v npm >/dev/null 2>&1 || { echo "==> Node.js kuruluyor"; brew install node; }

echo "==> Python 3.12 ortamı ve backend paketleri kuruluyor (ilk seferde birkaç dakika sürebilir)"
cd backend
[ -d .venv ] || uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
[ -f .env ] || { cp .env.example .env; echo "==> backend/.env oluşturuldu."; }
cd ..

echo "==> Arayüz paketleri kuruluyor ve derleniyor"
cd frontend
npm install
npm run build
cd ..

echo ""
echo "Kurulum tamamlandı."
echo "Uygulamayı başlatmak için:  ./start.sh"
echo "(Tarayıcı açıldığında Claude API anahtarınızı sizden isteyecek; anahtarınız yoksa"
echo " https://platform.claude.com/settings/keys adresinden ücretsiz oluşturabilirsiniz.)"
