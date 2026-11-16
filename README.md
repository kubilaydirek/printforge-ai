# PrintForge AI — Text-to-STL Agent Studio

Türkçe yazdığınız fikri, **4 uzman yapay zekâ ajanının** birlikte çalıştığı bir akışla
**Creality Ender 5 S1** (220 × 220 × 280 mm) için baskıya hazır **STL** dosyasına dönüştüren yerel web uygulaması.

Açık kaynak ve ücretsizdir ([LICENSE](LICENSE)); kendi bilgisayarınızda çalışır, verileriniz hiçbir sunucuya
gitmez. Çalıştırmak için tek ihtiyacınız olan bir **Claude API anahtarı** — uygulamayı ilk açtığınızda tarayıcı
sizden anahtarı ister ve kaydeder, başka bir ayar yapmanız gerekmez (bkz. [Kurulum](#2-adım-adım-kurulum-sıfırdan-macos)).

```
"Masama kulaklık tutucu yap"
        │
        ▼
┌──────────────────────┐   Teknik Tasarım Planı (JSON): bileşenler, mm ölçüler,
│ 1. Mimari Planlayıcı │── baskı yönü, birleşme koordinatları, kritik özellikler
└──────────┬───────────┘
           ▼
┌──────────────────────┐   build123d (OpenCascade) Python kodu
│ 2. CAD Mühendisi     │◄──────────────────────────────┐
└──────────┬───────────┘                               │ hata listesi + traceback
           ▼                                           │ (en fazla 4 deneme/tur)
┌──────────────────────┐   izole süreçte çalıştır → STL │
│ 3. Kod & Geometri    │── su geçirmezlik, kopuk parça, ┘
│    Denetçisi         │   tabla sınırı, Z=0 teması, 45° çıkıntı, duvar kalınlığı
└──────────┬───────────┘
           ▼ geçerli STL
┌──────────────────────┐   Ön/Yan/Üst/İzometrik PNG → Claude Vision:
│ 4. Görsel Denetçi    │── "İstenen parça bu mu? Orantısız, eksik, havada kalmış
│    (VLM)             │    ya da basılamayacak bir kusur var mı?"
└──────────┬───────────┘
   onay ✓  │  ✗ kusur → somut düzeltme notları Ajan 2'ye (en fazla 3 revizyon)
           ▼
     final.stl  →  3D önizleme + "STL İndir"
```

Ajanlar ortak bir durum nesnesini (`WorkflowState`: istek, plan, kod, deneme geçmişi, doğrulama ve denetim
raporları, en iyi aday) paylaşır. Her adım canlı olarak (Server-Sent Events) arayüze akar.

---

## 1. Proje klasör yapısı

```
printforge-ai/
├── README.md
├── setup.sh                     # tek seferlik kurulum (macOS)
├── start.sh                     # uygulamayı başlatır → http://localhost:8000
├── backend/
│   ├── requirements.txt
│   ├── .env.example             # → .env olarak kopyalanır, API anahtarı buraya
│   ├── main.py                  # FastAPI sunucusu (API + SSE + dosyalar + arayüz)
│   ├── data/jobs/<iş-id>/       # (otomatik) her denemenin kodu, STL'leri, render'ları
│   └── app/
│       ├── config.py            # tabla ölçüleri, kurallar, model ve limitler
│       ├── llm.py               # Claude API istemcisi (yapılandırılmış JSON çıktısı)
│       ├── state.py             # Job / DesignSession / WorkflowState (paylaşılan durum)
│       ├── orchestrator.py      # 4 ajanlı iş akışı ve revizyon döngüleri
│       ├── agents/
│       │   ├── planner.py       # Ajan 1 - Mimari Planlayıcı
│       │   ├── cad_coder.py     # Ajan 2 - CAD Mühendisi (build123d)
│       │   ├── validator.py     # Ajan 3 - Kod & Geometri Denetçisi
│       │   └── inspector.py     # Ajan 4 - Görsel Kalite Kontrol (Vision)
│       └── cad/
│           ├── sandbox.py       # güvenlik politikası + izole alt süreç
│           ├── runner.py        # alt süreçte kodu çalıştırıp STL üretir
│           ├── geometry.py      # trimesh ile basılabilirlik analizi
│           └── render.py        # headless 4 açılı PNG render (matplotlib)
└── frontend/
    ├── package.json
    ├── vite.config.js
    ├── index.html
    └── src/
        ├── main.jsx
        ├── App.jsx
        ├── api.js               # REST + canlı olay akışı (EventSource)
        ├── jobState.js          # ajan olaylarını arayüz durumuna çevirir
        ├── styles.css           # koyu tema
        └── components/
            ├── ChatPanel.jsx     # sohbet + örnek istekler
            ├── AgentTracker.jsx  # canlı ajan takibi, kontrol fotoğrafları, plan, kod
            ├── Viewer3D.jsx      # Ender 5 S1 tablası, STL modeli, ölçüler, STL İndir
            └── ApiKeyGate.jsx    # ilk açılışta Claude API anahtarı istemi
```

---

## 2. Adım adım kurulum (sıfırdan, macOS)

Aşağıdaki her komutu **Terminal** uygulamasına (Spotlight → "Terminal") yapıştırıp Enter'a basın.

**Adım 1 — Homebrew** (Mac için paket yöneticisi; zaten kuruluysa atlayın).
<https://brew.sh> sayfasındaki tek satırlık komutu Terminal'e yapıştırın ve yönergeleri izleyin.

**Adım 2 — Projeyi indirin**

```bash
git clone https://github.com/kubilaydirek/printforge-ai.git
cd printforge-ai
```

(Veya GitHub sayfasından "Code → Download ZIP" ile indirip klasörü açın.)

**Adım 3 — Kurulumu çalıştırın** (Python 3.12, CAD kütüphaneleri, Node.js ve arayüz; ilk seferde 3-10 dk)

```bash
./setup.sh
```

**Adım 4 — Uygulamayı başlatın**

```bash
./start.sh
```

Tarayıcı otomatik olarak <http://localhost:8000> adresini açar. İlk açılışta sizden **Claude API
anahtarınızı** ister:

1. Anahtarınız yoksa <https://platform.claude.com/settings/keys> adresinden bir tane oluşturun.
2. Anahtarı tarayıcıdaki kutuya yapıştırıp "Devam et"e basın.

Anahtar, bu bilgisayarda `backend/.env` dosyasına kaydedilir ve bir daha sorulmaz; hiçbir sunucuya ya da
üçüncü tarafa gönderilmez. Durdurmak için Terminal'de `Ctrl + C`. Bir sonraki kullanımda sadece bu adım
(`./start.sh`) yeterlidir.

> **Claude Pro/Max aboneliğiniz varsa** API kredisi harcamadan da çalıştırabilirsiniz: bu bilgisayarda
> [Claude Code](https://claude.com/claude-code) kurup `claude` → `/login` ile giriş yapın; `backend/.env`
> içinde `LLM_BACKEND=subscription` iken (varsayılan) uygulama otomatik olarak aboneliğinizi kullanır ve
> API anahtarı istemez.

---

## 3. Kullanım

1. Sol alttaki kutuya fikrinizi yazın (ör. *"Masama kulaklık tutucu yap"*) veya örnek isteklerden birine tıklayın.
2. **Canlı ajan akışı** kartında hangi ajanın ne yaptığını, hataların nasıl düzeltildiğini ve Görsel Denetçi'nin
   çektiği 4 kontrol fotoğrafını görürsünüz (fotoğrafa tıklayınca büyür).
3. İlk geçerli STL üretildiği anda sağdaki 220 × 220 mm tablada **canlı önizleme** belirir; fareyle
   döndürün (sol tık), kaydırın (sağ tık), yakınlaştırın (tekerlek). X / Y / Z ölçüleri mm cinsinden gösterilir.
4. Onaydan sonra sağ üstteki **⬇ STL İndir** ile dosyayı alın ve Creality Print / Cura'da dilimleyin.
5. Değişiklik için aynı sohbete yazın (ör. *"kancayı 15 mm uzat, tabanı genişlet"*). Ajanlar mevcut planı ve
   kodu temel alarak revize eder. Sıfırdan başlamak için **+ Yeni tasarım**.

Kartın altındaki **Teknik plan (JSON)** ve **build123d kodu** sekmeleri, ajanların ürettiği planı ve kodu gösterir.
Her işin tüm ara çıktıları `backend/data/jobs/<iş-id>/` klasöründedir (`final.stl`, `final_design.py`, render'lar).

---

## 4. Ayarlar (`backend/.env`)

| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `LLM_BACKEND` | `subscription` | `subscription`: Claude Pro/Max aboneliği (Claude Code üzerinden) · `api`: kredili API anahtarı |
| `CLAUDE_CLI_MODEL` | boş | Abonelik modunda model (`opus`, `sonnet`…); boşsa planınızın varsayılanı |
| `CLI_TIMEOUT_S` | `900` | Abonelik modunda tek ajan cevabı için bekleme sınırı (sn) |
| `ANTHROPIC_API_KEY` | — | Sadece `api` modunda gerekli; tarayıcıdaki anahtar istemine girilince otomatik yazılır |
| `CLAUDE_MODEL` | `claude-opus-5-5` | `api` modunda kullanılan model |
| `EFFORT_PLANNER` / `EFFORT_CODER` / `EFFORT_INSPECTOR` | `medium` / `high` / `medium` | Ajan başına düşünme derinliği (`low`…`max`) |
| `MAX_VISUAL_REVISIONS` | `3` | Görsel denetçinin isteyebileceği otonom revizyon sayısı |
| `MAX_FIX_ATTEMPTS` | `4` | Her turda kod/geometri hatası için düzeltme denemesi |
| `EXEC_TIMEOUT_S` | `120` | Üretilen CAD kodunun süre sınırı |

Bir tasarım tipik olarak 4-10 Claude çağrısı kullanır (plan + kod denemeleri + görsel denetimler) ve
birkaç dakika sürer. Abonelik modunda bu kullanım planınızın Claude Code limitlerinden düşer; limit dolarsa
sıfırlanmasını beklemeniz gerekir. API modunda kullanım kredinizden ücretlendirilir.

---

## 5. Uygulanan baskı kuralları (Ender 5 S1)

- **Baskı hacmi** 220 × 220 × 280 mm — aşılırsa model reddedilip küçültülür.
- **Tabana oturma:** model XY'de tabla merkezine alınır, en alt noktası Z = 0'a indirilir; tabla temas alanı
  10 mm²'den küçükse reddedilir.
- **Tek parça / kopuk parça yok:** su geçirmez (manifold) olmayan veya tabana değmeyen gövdeler reddedilir.
- **Minimum duvar 1,5 mm:** yüzeyden içe ışın atılarak ölçülür; ince bölgeler uyarı veya ret sebebidir.
- **45° kuralı:** 45°'den dik aşağı bakan yüzey alanı ölçülür; fazlaysa Görsel Denetçi'ye ve CAD Mühendisi'ne bildirilir.

---

## 6. Sorun giderme

- **API anahtarı isteyen ekran kapanmıyor / "Geçersiz Claude API anahtarı":** anahtarı
  <https://platform.claude.com/settings/keys> sayfasından kopyaladığınızdan ve hesabınızda kredi olduğundan
  emin olun.
- **"Claude aboneliği hazır değil" uyarısı:** Terminal'de `claude auth status` çalıştırın; giriş yoksa `claude`
  → `/login`, sonra ekrandaki "yeniden kontrol edin" bağlantısına basın.
- **"Kullanım limitine ulaşıldı":** aboneliğinizin Claude Code limiti dolmuştur; sıfırlanınca tekrar deneyin.
- **"Credit balance is too low":** `api` modundasınız ve API hesabında kredi yok; `backend/.env` içinde
  `LLM_BACKEND=subscription` yapıp Claude Code ile giriş yapın.
- **`Address already in use` (port 8000 dolu):** önceki pencere hâlâ açık olabilir; o Terminal'de `Ctrl + C`.
- **Model istediğiniz gibi değil:** ölçü verin ("taban 100 × 80 mm, yükseklik 150 mm") veya sohbetten revize isteyin.
- **Geliştirici modu (anlık yenilenen arayüz):** bir Terminal'de `backend/.venv/bin/python backend/main.py`,
  diğerinde `npm --prefix frontend run dev` çalıştırıp <http://localhost:5173> adresini açın.

**Güvenlik notu:** Yapay zekânın yazdığı CAD kodu, yalnızca CAD/matematik modüllerine izin veren bir statik
denetimden geçer ve süre/CPU sınırlı ayrı bir süreçte çalışır. Bu, tek kullanıcılı yerel kullanım için makul bir
korumadır; tam bir sanal makine izolasyonu değildir. Sunucu yalnızca `127.0.0.1` üzerinde dinler.

---

## 7. Lisans

[MIT](LICENSE) — kopyalayın, değiştirin, dağıtın; kendi Claude anahtarınızla ücretsiz kullanın.
