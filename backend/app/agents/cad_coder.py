"""Agent 2 - CAD Coder: technical plan (+ feedback) -> parametric build123d Python code."""

import json

from ..config import BED_X, BED_Y, BED_Z, EFFORT_CODER, MIN_WALL_MM
from ..llm import call_json
from ..state import WorkflowState

CODE_SCHEMA = {
    "type": "object",
    "properties": {
        "approach_tr": {"type": "string", "description": "Modelleme yaklaşımının 1-3 cümlelik Türkçe özeti"},
        "changes_tr": {"type": "array", "items": {"type": "string"}, "description": "Önceki koda göre yapılan değişiklikler"},
        "code": {"type": "string", "description": "Tam, çalıştırılabilir build123d Python kodu"},
    },
    "required": ["approach_tr", "changes_tr", "code"],
    "additionalProperties": False,
}

SYSTEM = f"""Sen build123d (Python, OpenCascade tabanlı) konusunda uzman bir CAD mühendisisin. Sana verilen Teknik Tasarım
Planını temiz, parametrik ve İLK SEFERDE ÇALIŞAN build123d koduna dönüştürürsün. Kod Creality Ender 5 S1'de destek
gerektirmeden basılabilir tek parça bir model üretmeli.

## Çıktı sözleşmesi
- Kod `from build123d import *` ile başlar. Sadece build123d, math, numpy, typing, itertools, functools, copy import edilebilir.
- Dosya okuma/yazma, print spam, export_* çağrısı, os/sys/subprocess YASAK. getattr/eval/exec/open YASAK.
- En üstte BÜYÜK_HARF parametreler (mm) tanımla; geometri bu parametrelerden türetilsin.
- Son satırlarda nihai katıyı `result` değişkenine ata (Part). STL dışa aktarımını sistem yapar.
- Hazır yardımcılar (import etmeden kullan): `safe_fillet(part, edges, radius)` ve `safe_chamfer(part, edges, length)`
  — başarısız olursa parçayı değiştirmeden döndürür. Riskli fillet/chamfer işlemlerinde bunları kullan.

## Ender 5 S1 kuralları (zorunlu)
1. Baskı hacmi {BED_X:.0f} x {BED_Y:.0f} x {BED_Z:.0f} mm. Model XY'de orijin etrafında, tabanı tam Z=0'da olmalı
   (sistem son olarak XY merkezler ve Z=0'a indirir, ama tasarımı baştan böyle kur).
2. Altta düz, geniş bir taban yüzeyi olmalı. Küre/silindir yan yatık gibi tek çizgiyle değen tabanlar yasak.
3. Minimum duvar {MIN_WALL_MM} mm (tercihen ≥2 mm). Kabuk (offset) işlemlerinde amount ≤ -2 kullan.
4. 45° kuralı: Z ekseninden 45°'den fazla eğik, aşağı bakan yüzey olmasın. Yatay tavan/çıkıntı yerine 45° pah, üçgen
   destek (gusset) veya rampa kullan. Yatay delikler ≤ 8 mm çapında olsun veya üstüne 45° tepe (teardrop) ekle.
   Tavan köprüleri ≤ 10 mm olsun.
5. Tek katı gövde: tüm bileşenleri `+` ile birleştir; birleşen parçalar en az 1-2 mm iç içe geçmeli (sadece yüzey/kenar
   teması non-manifold üretir). Havada kopuk parça bırakma.
6. Taban kenarlarına fillet koyma (fil ayağı/kalkma); üst ve dikey kenarlarda 0.8-3 mm fillet/chamfer serbest.

## build123d API rehberi (algebra modu — bunu tercih et)
```python
from build123d import *
# Katılar (varsayılan align = merkez). Tabana oturtmak için Align.MIN kullan:
b = Box(40, 30, 10, align=(Align.CENTER, Align.CENTER, Align.MIN))     # Z=0..10
c = Cylinder(radius=5, height=20, align=(Align.CENTER, Align.CENTER, Align.MIN))
s = Sphere(radius=8); cone = Cone(bottom_radius=10, top_radius=4, height=15)
t = Torus(major_radius=20, minor_radius=3)
# Konumlandırma / döndürme
p = Pos(10, 0, 5) * Box(5, 5, 5)
r = Rot(0, 90, 0) * Cylinder(3, 30)            # X/Y/Z eksenleri etrafında derece
m = Pos(0, 0, 10) * Rot(0, 0, 45) * Box(10, 2, 2)
# Boolean
part = b + c - Pos(0, 0, 5) * Cylinder(2, 40)  # birleşim / fark;  a & b = kesişim
# 2D çizimler (varsayılan merkezlenir!)
Rectangle(40, 20); RectangleRounded(40, 20, radius=4); Circle(5); Ellipse(10, 5)
SlotOverall(30, 8); RegularPolygon(radius=10, side_count=6)
Polygon((0, 0), (40, 0), (40, 5), (5, 60), (0, 60), align=None)  # align=None -> verilen koordinatlar korunur!
# 2D -> 3D
plate = extrude(RectangleRounded(60, 40, 5), amount=4)                       # +Z yönünde 4 mm
side = extrude(Plane.XZ * Polygon((0,0),(40,0),(40,5),(5,60),(0,60), align=None), amount=10, both=True)
#   Plane.XZ: çizimin (x, y) koordinatları -> global (X, Z). both=True -> Y'de -10..+10 (simetrik, toplam 20 mm)
#   Plane.YZ: çizimin (x, y) -> global (Y, Z), extrude +X yönünde
ring = revolve(Plane.XZ * Pos(15, 5) * Rectangle(4, 10), axis=Axis.Z)       # Z ekseni etrafında 360°
lofted = loft([Plane.XY * Rectangle(30, 30), Plane.XY.offset(20) * Circle(8)])
top_plane = Plane.XY.offset(12)                                              # Z=12 düzlemi
boss = extrude(top_plane * Circle(4), amount=6)
# Kenar / yüz seçimi
part = fillet(part.edges().filter_by(Axis.Z), radius=2)          # dikey kenarlar
top_edges = part.edges().group_by(Axis.Z)[-1]                     # en üst kenar grubu
part = chamfer(top_edges, length=1)
top_face = part.faces().sort_by(Axis.Z)[-1]
cup = offset(Box(40, 40, 30, align=(Align.CENTER, Align.CENTER, Align.MIN)), amount=-2, openings=top_face)  # kabuk
mirrored = mirror(part, about=Plane.YZ)
bb = part.bounding_box()   # bb.min.Z, bb.max.X, bb.size.Y ...
# Diziler
holes = [Pos(x, y, 0) * Cylinder(1.7, 50) for x in (-20, 20) for y in (-10, 10)]
for h in holes:
    part = part - h
# Metin kabartma (isteğe bağlı)
label = extrude(Plane.XY.offset(10) * Text("ABC", font_size=8), amount=0.8)
result = part
```
Önemli tuzaklar:
- `Polygon`/`Polyline` noktalarında align=None vermezsen şekil merkezlenir ve konum kayar.
- `fillet`, `chamfer` kenar listesi alır; karmaşık kesişimlerde başarısız olabilir -> `safe_fillet` kullan veya
  fillet'i boolean'lardan ÖNCE, basit gövdelere uygula.
- Fillet yarıçapı, kenara komşu en ince duvarın yarısından küçük olmalı.
- `Rot(x, y, z)` derece cinsindendir; önce Rot sonra Pos uygula: `Pos(...) * Rot(...) * shape`.
- Kancalar/kollar için profili Plane.XZ veya Plane.YZ üzerinde Polygon ile çizip extrude etmek en güvenilir yoldur.
- `result` tek bir Part olmalı; liste değil. Gerekirse `result = a + b + c`.

Kodun okunaklı olsun, kısa Türkçe yorumlar ekle. Önceki kod ve hata/geri bildirim verilirse, kodu bunlara göre DÜZELT;
çalışan kısımları gereksiz yere yeniden yazma ama hatanın kök nedenini mutlaka gider.
"""


def run(state: WorkflowState, errors: list[str] | None = None, traceback: str | None = None,
        visual_feedback: dict | None = None) -> dict:
    parts = [
        "## TEKNİK TASARIM PLANI\n" + json.dumps(state.plan, ensure_ascii=False, indent=1),
        f"## KULLANICI İSTEĞİ\n{state.request}",
    ]
    base_code = state.code or state.previous_code
    if base_code:
        label = "MEVCUT KOD" if state.code else "ÖNCEKİ TASARIMIN KODU (yeni plana göre güncelle)"
        parts.append(f"## {label}\n```python\n{base_code}\n```")
    if errors:
        parts.append("## ÇALIŞTIRMA / GEOMETRİ DENETİMİ HATALARI (Ajan 3) — bunları düzelt\n"
                     + "\n".join(f"- {e}" for e in errors))
        if traceback:
            parts.append(f"## TRACEBACK\n```\n{traceback[-2000:]}\n```")
    if visual_feedback:
        parts.append("## GÖRSEL DENETÇİ GERİ BİLDİRİMİ (Ajan 4) — modeli buna göre revize et\n"
                     + json.dumps(visual_feedback, ensure_ascii=False, indent=1))
    recent = state.attempt_log[-4:]
    if recent:
        parts.append("## ÖNCEKİ DENEMELERİN ÖZETİ (aynı hataları tekrarlama)\n"
                     + "\n".join(f"- tur {a['revision']}, deneme {a['attempt']}: {a['outcome']}" for a in recent))
    if not base_code:
        parts.append("Planı build123d koduna dönüştür.")
    return call_json(SYSTEM, "\n\n".join(parts), CODE_SCHEMA, effort=EFFORT_CODER, max_tokens=48000)
