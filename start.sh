#!/usr/bin/env bash
# PrintForge AI - uygulamayı başlatır ve tarayıcıda açar: http://localhost:8000
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x backend/.venv/bin/python ]; then
  echo "Önce kurulumu çalıştırın:  ./setup.sh"
  exit 1
fi
if grep -qE '^LLM_BACKEND=api' backend/.env 2>/dev/null; then
  grep -qE '^ANTHROPIC_API_KEY=sk-ant-[A-Za-z0-9]' backend/.env || echo "UYARI: API modu seçili ama backend/.env içinde ANTHROPIC_API_KEY yok."
elif ! command -v claude >/dev/null 2>&1 && [ ! -x "$HOME/.local/bin/claude" ]; then
  echo "UYARI: 'claude' komutu bulunamadı. Abonelik modu için Claude Code kurulu ve giriş yapılmış olmalı."
fi
npm --prefix frontend run build >/dev/null

(sleep 2 && open "http://localhost:8000") >/dev/null 2>&1 &
echo "PrintForge AI çalışıyor: http://localhost:8000  (durdurmak için Ctrl+C)"
exec backend/.venv/bin/python backend/main.py
