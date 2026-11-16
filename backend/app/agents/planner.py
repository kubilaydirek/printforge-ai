"""Agent 1 - Design Planner: Turkish request -> structured technical design plan (JSON)."""

import json

from ..config import BED_X, BED_Y, BED_Z, EFFORT_PLANNER, MIN_WALL_MM
from ..llm import call_json, image_ref
from ..state import WorkflowState

_XYZ = {
    "type": "object",
    "properties": {"x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}},
    "required": ["x", "y", "z"],
    "additionalProperties": False,
}

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "object_name": {"type": "string", "description": "Kısa, dosya adına uygun İngilizce ad (snake_case)"},
        "title_tr": {"type": "string"},
        "summary_tr": {"type": "string"},
        "intended_use": {"type": "string"},
        "assumptions": {"type": "array", "items": {"type": "string"}},
        "overall_dimensions_mm": _XYZ,
        "print_orientation": {"type": "string"},
        "material_suggestion": {"type": "string"},
        "max_bodies": {"type": "integer", "description": "STL'deki ayrı gövde sayısı üst sınırı (genelde 1)"},
        "components": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "role": {"type": "string"},
                    "shape": {"type": "string", "description": "Geometri tarifi: kutu, silindir, profil extrude, revolve..."},
                    "parameters": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"name": {"type": "string"}, "value_mm": {"type": "number"}},
                            "required": ["name", "value_mm"],
                            "additionalProperties": False,
                        },
                    },
                    "bbox_mm": _XYZ,
                    "position_mm": _XYZ,
                    "connects_to": {"type": "array", "items": {"type": "string"}},
                    "notes": {"type": "string"},
                },
                "required": ["name", "role", "shape", "parameters", "bbox_mm", "position_mm", "connects_to", "notes"],
                "additionalProperties": False,
            },
        },
        "joints": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "between": {"type": "array", "items": {"type": "string"}},
                    "method": {"type": "string"},
                    "overlap_mm": {"type": "number"},
                },
                "required": ["between", "method", "overlap_mm"],
                "additionalProperties": False,
            },
        },
        "printability_notes": {"type": "array", "items": {"type": "string"}},
        "critical_features": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "object_name", "title_tr", "summary_tr", "intended_use", "assumptions", "overall_dimensions_mm",
        "print_orientation", "material_suggestion", "max_bodies", "components", "joints",
        "printability_notes", "critical_features",
    ],
    "additionalProperties": False,
}

SYSTEM = f"""Sen kıdemli bir mekanik tasarım ve 3D baskı (FDM) mühendisisin. Görevin, 3D çizim bilmeyen bir kullanıcının
Türkçe yazdığı basit isteği, bir CAD mühendisinin doğrudan koda dökebileceği kesin bir Teknik Tasarım Planına dönüştürmek.

Yazıcı: Creality Ender 5 S1, baskı hacmi {BED_X:.0f} x {BED_Y:.0f} x {BED_Z:.0f} mm, 0.4 mm nozul, PLA/PETG.

Koordinat sistemi (zorunlu):
- Z yukarı. Baskı tablası Z=0 düzlemi. Tabla merkezi X=0, Y=0.
- Model baskı yönünde tasarlanır: en geniş düz yüzey tabana (Z=0) oturur.
- position_mm = bileşenin sınır kutusunun (bounding box) MERKEZİ, global koordinatta.
- bbox_mm = bileşenin X/Y/Z boyutları.

Tasarım kuralları:
1. Gerçek dünya ölçülerini kullan (ör. kulaklık bandı ~35-45 mm genişlik, masa kalınlığı 15-40 mm, telefon 75x8-12 mm,
   M3 vida deliği 3.4 mm, M4 4.5 mm, kalem çapı ~8-11 mm). Belirsiz ölçüleri makul varsayımlarla seç ve assumptions'a yaz.
2. Minimum duvar kalınlığı {MIN_WALL_MM} mm; yapısal kısımlarda 2.5-4 mm, taşıyıcı kollarda 4-8 mm tercih et.
3. Destek (support) gerektirmeyecek tasarla: yatay çıkıntılar yerine en fazla 45° eğimli pah/rampalar, yatay delikler için
   küçük çap veya damla (teardrop) formu. Köprüler 10 mm'yi geçmesin.
4. Tüm bileşenler TEK katı gövde olarak birleşmeli: birleşen parçalar birbirine en az 1-2 mm iç içe geçsin (overlap_mm).
   Havada kalan, sadece kenar/nokta ile değen parça olmasın. Birden fazla ayrı parça (ör. kutu + kapak) gerçekten
   gerekiyorsa tablaya yan yana yerleştir ve max_bodies değerini buna göre ver; aksi halde max_bodies = 1.
5. Geçme toleransı: hareketli/geçmeli yüzeyler arasında 0.3-0.4 mm boşluk bırak.
6. Model baskı hacmine sığmalı; sığmıyorsa ölçeği küçült ve bunu assumptions'ta açıkla.
7. Kenarlara 1-3 mm pah/yuvarlatma öner (dayanıklılık + estetik), ama taban kenarında yuvarlatma yerine küçük pah kullan.

Alanlar: title_tr, summary_tr, intended_use, assumptions, print_orientation, material_suggestion, notes, printability_notes,
critical_features alanlarını Türkçe yaz. critical_features: görsel denetçinin mutlaka kontrol etmesi gereken özellikler
(ör. "kanca ucu yukarı kalkık", "masa kelepçesi açıklığı 30 mm"). Bileşen isimleri kısa ve İngilizce snake_case olsun.

Kullanıcı bir ürün fotoğrafı eklerse (ör. internette STL'i bulunmayan bir ürün): fotoğraf(lar)ı dikkatle incele ve
nesneyi olduğu gibi yeniden üretecek bir plan çıkar.
- Genel formu, parça sayısını, simetriyi, delik/çentik/kanca/menteşe gibi detayları ve yüzey geçişlerini görseldeki
  gibi modelle; kullanıcı metninde aksini belirtmediği sürece fotoğraftan sapma.
- Mutlak ölçüyü fotoğraftan kesin çıkaramayacağın için, görseldeki tanıdık referans nesnelerden (el, parmak, USB
  girişi, priz, bozuk para, standart vida/cıvata, A4 kağıt, telefon vb.) veya nesnenin bilinen tipik boyutundan
  oranlayarak gerçekçi bir ölçü tahmini yap; tahminini ve dayandığı referansı assumptions'a açıkça yaz.
  Kullanıcı metninde bir ölçü verilmişse (ör. "çapı 40 mm") o ölçüyü esas al ve diğerlerini orana göre ölçekle.
- Fotoğraftaki nesneyi FDM yazıcıda basılabilir hale getirmek için gereken düzeltmeleri (duvar kalınlığı, 45° kuralı,
  destek gerektiren çıkıntıları doldurma/köprüleme, ince/kırılgan detayları kalınlaştırma) uygula ve bunları
  printability_notes'a yaz; görsel sadeleştirme yaptıysan assumptions'ta belirt.
- Fotoğrafta net görünmeyen iç yapı/arka yüz gibi kısımlar için makul ve işlevsel bir varsayım yap, assumptions'a yaz.
- Kullanıcı metni boşsa veya sadece "bunun STL'ini çıkar" gibi ise, isteği tamamen fotoğraftan türet.
  Metin varsa, fotoğrafı temel alıp metindeki talimatları (ölçü, değişiklik, ek özellik) üzerine uygula.
"""


def _request_text(state: WorkflowState) -> str:
    if state.request.strip():
        return state.request
    return "(Metin verilmedi; yalnızca ekli ürün fotoğrafı/fotoğrafları verildi. Görseldeki nesnenin baskıya hazır STL'ini çıkaracak bir plan oluştur.)"


def run(state: WorkflowState) -> dict:
    parts = []
    if state.previous_plan:
        parts.append("MEVCUT TASARIM PLANI (kullanıcı bunu revize etmek istiyor, uygun olanları koru):\n"
                     + json.dumps(state.previous_plan, ensure_ascii=False, indent=1))
        if len(state.history) > 1:
            parts.append("ÖNCEKİ İSTEKLER:\n" + "\n".join(f"- {h}" for h in state.history[:-1]))
        parts.append(f"YENİ REVİZYON İSTEĞİ: {_request_text(state)}\n\nGüncellenmiş TAM planı döndür.")
    else:
        parts.append(f"KULLANICI İSTEĞİ: {_request_text(state)}")

    if not state.reference_images:
        return call_json(SYSTEM, "\n\n".join(parts), PLAN_SCHEMA, effort=EFFORT_PLANNER)

    content: list[dict] = [{"type": "text", "text": "\n\n".join(parts)}]
    for i, path in enumerate(state.reference_images, 1):
        content.append({"type": "text", "text": f"Referans ürün fotoğrafı {i}/{len(state.reference_images)}:"})
        content.append(image_ref(path))
    content.append({"type": "text", "text": "Yukarıdaki fotoğraf(lar)ı analiz ederek Teknik Tasarım Planını oluştur."})
    return call_json(SYSTEM, content, PLAN_SCHEMA, effort=EFFORT_PLANNER)
