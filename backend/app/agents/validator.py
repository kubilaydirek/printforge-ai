"""Agent 3 - Execution & Sanity Validator: runs the code, exports STL, checks printability.

Deterministic (no LLM): the verdict comes from the CAD kernel and mesh analysis, and any
failure is routed back to the CAD Coder with precise, actionable error messages.
"""

from pathlib import Path

from ..cad import geometry, sandbox


def run(code: str, work_dir: Path, max_bodies: int) -> dict:
    report: dict = {"ok": False, "stage": "policy", "errors": [], "warnings": [], "metrics": {}, "traceback": None}

    problems = sandbox.check_policy(code)
    if problems:
        report["errors"] = problems
        return report

    report["stage"] = "execute"
    info = sandbox.execute(code, work_dir)
    if not info.get("ok"):
        where, src_line = "", ""
        if info.get("line"):
            where = f" (design.py satır {info['line']})"
            lines = code.splitlines()
            if 0 < info["line"] <= len(lines):
                src_line = f" | hatalı satır: `{lines[info['line'] - 1].strip()}`"
        msg = info.get("error") or (
            "OpenCascade geometri işlemi başarısız (genelde geçersiz ölçü, çok büyük fillet/chamfer yarıçapı, "
            "kendi kendini kesen profil veya teğet/sıfır kalınlıklı boolean)"
            if "Standard" in str(info.get("error_type")) else "mesaj yok")
        report["errors"] = [f"{info.get('error_type', 'Hata')}{where}: {msg}{src_line}"]
        report["traceback"] = info.get("traceback")
        return report
    if not info.get("is_valid", True):
        report["warnings"].append("OpenCascade katıyı geçersiz (invalid) olarak işaretledi; boolean/fillet işlemlerini kontrol et.")

    report["stage"] = "geometry"
    model_path, preview_path = work_dir / "model.stl", work_dir / "preview.stl"
    mesh, shift = geometry.normalize_on_bed(model_path, preview_path)
    if abs(shift[2]) > 0.05:
        report["warnings"].append(f"Model tabla seviyesine taşındı (Z kaydırma {shift[2]:+.2f} mm).")

    analysis = geometry.analyze(mesh, max_bodies=max(1, int(max_bodies or 1)))
    report["errors"] = analysis["errors"]
    report["warnings"] += analysis["warnings"]
    report["metrics"] = {**analysis["metrics"], "cad_solids": info.get("solid_count")}
    report["ok"] = not report["errors"]
    report["stl_path"] = str(model_path)
    report["preview_path"] = str(preview_path)
    return report
