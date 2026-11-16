"""Agent 4 - Visual Inspector (VLM): judges 4 rendered views against the request and plan."""

import json

from ..config import EFFORT_INSPECTOR
from ..llm import call_json, image_ref
from ..state import WorkflowState

INSPECTION_SCHEMA = {
    "type": "object",
    "properties": {
        "approved": {"type": "boolean"},
        "score": {"type": "integer", "description": "1-10 arası genel kalite puanı"},
        "matches_request": {"type": "boolean"},
        "summary_tr": {"type": "string"},
        "observations_tr": {"type": "array", "items": {"type": "string"}},
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "severity": {"type": "string", "enum": ["critical", "major", "minor"]},
                    "category": {
                        "type": "string",
                        "enum": ["wrong_shape", "missing_feature", "proportion", "floating", "printability", "dimension", "other"],
                    },
                    "description_tr": {"type": "string"},
                    "fix_instruction": {"type": "string", "description": "CAD mühendisi için somut, ölçülü düzeltme talimatı"},
                },
                "required": ["severity", "category", "description_tr", "fix_instruction"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["approved", "score", "matches_request", "summary_tr", "observations_tr", "issues"],
    "additionalProperties": False,
}

SYSTEM = """Sen titiz bir 3D baskı kalite kontrol mühendisisin. Sana bir CAD modelinin 4 farklı açıdan (Ön, Yan, Üst,
İzometrik; ortografik) render görüntüleri, kullanıcının isteği, teknik tasarım planı ve otomatik geometri ölçümleri verilir.
Turuncu cisim modeldir; altındaki gri-mavi düzlem baskı tablasıdır (Z=0).

Cevaplaman gereken soru: "Kullanıcının istediği parça bu mu? Orantısız, eksik, havada kalmış veya 3D yazıcıda
basılamayacak bir kusur var mı?"

Bazen kullanıcının orijinal referans ürün fotoğrafı da verilir (STL'i olmayan, internette bulduğu bir ürün). Bu durumda
asıl soru: "Render edilen model, referans fotoğraftaki ürünle aynı mı?" — form, oran, parça sayısı ve belirgin
detaylar (delik, kanca, menteşe, çentik vb.) fotoğrafla eşleşmeli. Baskı için zorunlu küçük sadeleştirmeler
(destek gerektiren çıkıntının doldurulması gibi) kusur sayılmaz, ama fotoğraftaki nesneye hiç benzemeyen bir form kusurdur.

Değerlendirme yöntemi:
1. Önce her görüntüde ne gördüğünü kısaca not et (observations_tr).
2. Planın critical_features listesindeki her maddeyi görüntülerde doğrula.
3. Referans fotoğraf verildiyse, render'ları fotoğrafla karşılaştır: aynı nesne mi, oranlar ve detaylar uyuşuyor mu?
4. Gerçek kullanım senaryosunu düşün: bu parça işini görür mü (ör. kulaklık kancaya oturur mu, telefon tutucunun açısı
   ve dudağı var mı, kutu içi boş mu)?
5. Basılabilirlik: geniş düz taban, desteksiz çıkıntılar (45° kuralı), ince duvarlar, devrilme riski.
6. Ölçümleri (metrics) planla karşılaştır.

Karar kuralları:
- approved = true sadece critical ve major sorun yoksa. Küçük estetik (minor) sorunlar onayı engellemez.
- Render kaynaklı küçük gölgelendirme artefaktlarını kusur sayma.
- Her sorun için fix_instruction'ı CAD mühendisinin doğrudan uygulayabileceği şekilde somut yaz
  (hangi bileşen, hangi parametre, kaç mm, hangi yöne). Belirsiz "daha iyi yap" ifadeleri kullanma.
- Gereksiz yere reddetme: model isteği makul şekilde karşılıyorsa onayla.
"""


def run(state: WorkflowState, renders: list[dict], validation: dict) -> dict:
    plan = state.plan or {}
    brief = {
        "title": plan.get("title_tr"),
        "summary": plan.get("summary_tr"),
        "overall_dimensions_mm": plan.get("overall_dimensions_mm"),
        "print_orientation": plan.get("print_orientation"),
        "components": [{"name": c["name"], "role": c["role"], "bbox_mm": c["bbox_mm"]} for c in plan.get("components", [])],
        "critical_features": plan.get("critical_features"),
    }
    content: list[dict] = [{
        "type": "text",
        "text": f"KULLANICI İSTEĞİ: {state.request or '(yok, aşağıdaki referans fotoğraftan türetildi)'}\n\n"
                f"PLAN ÖZETİ:\n{json.dumps(brief, ensure_ascii=False, indent=1)}\n\n"
                f"OTOMATİK GEOMETRİ ÖLÇÜMLERİ:\n{json.dumps(validation.get('metrics', {}), ensure_ascii=False)}\n"
                f"UYARILAR: {json.dumps(validation.get('warnings', []), ensure_ascii=False)}\n\n"
                f"Bu {state.revision + 1}. denetim turu.",
    }]
    if state.reference_images:
        content.append({"type": "text", "text": "Kullanıcının referans ürün fotoğrafı/fotoğrafları (render'ları bununla karşılaştır):"})
        for path in state.reference_images:
            content.append(image_ref(path))
    for r in renders:
        content.append({"type": "text", "text": f"Render görüntüsü: {r['label']}"})
        content.append(image_ref(r["path"]))
    content.append({"type": "text", "text": "Modeli değerlendir ve kararını ver."})
    return call_json(SYSTEM, content, INSPECTION_SCHEMA, effort=EFFORT_INSPECTOR)
