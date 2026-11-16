"""Mesh-level printability analysis for the Ender 5 S1."""

import math
from pathlib import Path

import numpy as np
import trimesh

from ..config import BED_X, BED_Y, BED_Z, MAX_OVERHANG_DEG, MIN_BED_CONTACT_MM2, MIN_WALL_MM

BED_EPS = 0.05


def _load(path: Path) -> trimesh.Trimesh:
    mesh = trimesh.load_mesh(str(path), process=True)
    if isinstance(mesh, trimesh.Scene):
        mesh = trimesh.util.concatenate(list(mesh.geometry.values()))
    mesh.merge_vertices()
    return mesh


def normalize_on_bed(model_path: Path, preview_path: Path) -> tuple[trimesh.Trimesh, list[float]]:
    """Center XY on the bed origin and drop to Z=0. Rewrites both STL files."""
    mesh = _load(model_path)
    lo, hi = mesh.bounds
    shift = np.array([-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]])
    mesh.apply_translation(shift)
    mesh.export(str(model_path))
    if preview_path.exists():
        prev = _load(preview_path)
        prev.apply_translation(shift)
        prev.export(str(preview_path))
    return mesh, shift.tolist()


def _wall_thickness(mesh: trimesh.Trimesh, samples: int = 700) -> dict:
    """Ray-cast inward from sampled surface points; returns thin-area fractions."""
    try:
        points, face_idx = trimesh.sample.sample_surface(mesh, samples, seed=7)
        normals = mesh.face_normals[face_idx]
        origins = points - normals * 0.01
        locs, ray_idx, _ = mesh.ray.intersects_location(origins, -normals, multiple_hits=False)
        thickness = np.full(len(points), np.inf)
        if len(ray_idx):
            d = np.linalg.norm(locs - origins[ray_idx], axis=1) + 0.01
            thickness[ray_idx] = d
        finite = thickness[np.isfinite(thickness)]
        if finite.size == 0:
            return {"available": False}
        return {
            "available": True,
            "min_mm": float(np.min(finite)),
            "p5_mm": float(np.percentile(finite, 5)),
            "thin_fraction": float(np.mean(finite < MIN_WALL_MM)),
            "very_thin_fraction": float(np.mean(finite < 1.0)),
        }
    except Exception as e:  # rtree/embree missing or degenerate mesh
        return {"available": False, "reason": str(e)[:200]}


def analyze(mesh: trimesh.Trimesh, max_bodies: int) -> dict:
    errors: list[str] = []
    warnings: list[str] = []

    if len(mesh.faces) == 0:
        return {"errors": ["STL boş: hiç üçgen yok."], "warnings": [], "metrics": {}}

    ext = mesh.extents
    metrics: dict = {
        "size_mm": {"x": round(float(ext[0]), 2), "y": round(float(ext[1]), 2), "z": round(float(ext[2]), 2)},
        "triangles": int(len(mesh.faces)),
        "watertight": bool(mesh.is_watertight),
        "winding_consistent": bool(mesh.is_winding_consistent),
    }

    # 1) Bed limits
    if ext[0] > BED_X or ext[1] > BED_Y or ext[2] > BED_Z:
        errors.append(
            f"Model Ender 5 S1 baskı hacmini aşıyor: {ext[0]:.1f} x {ext[1]:.1f} x {ext[2]:.1f} mm "
            f"(sınır {BED_X:.0f} x {BED_Y:.0f} x {BED_Z:.0f} mm). Ölçüleri küçült veya döndür."
        )

    # 2) Manifold / watertight
    if not mesh.is_watertight:
        errors.append(
            "Mesh su geçirmez (watertight/manifold) değil: açık yüzeyler veya kesişen gövdeler var. "
            "Tüm parçaları boolean birleşim (+) ile tek katıya birleştir, sıfır kalınlıklı temaslardan kaçın."
        )

    # 3) Bodies & floating parts
    bodies = mesh.split(only_watertight=False)
    metrics["body_count"] = len(bodies)
    floating = [b for b in bodies if b.bounds[0][2] > BED_EPS]
    if floating:
        errors.append(
            f"{len(floating)} adet havada kopuk parça var (tabana değmiyor, en düşük Z = "
            f"{min(b.bounds[0][2] for b in floating):.2f} mm). Bu parçalar ana gövdeye birleşmeli."
        )
    if len(bodies) > max_bodies:
        errors.append(
            f"Model {len(bodies)} ayrı gövdeden oluşuyor, plan en fazla {max_bodies} gövdeye izin veriyor. "
            "Bileşenler birbirine en az 1-2 mm iç içe geçerek (overlap) birleşmeli."
        )

    # 4) Volume
    if mesh.is_watertight:
        vol = abs(float(mesh.volume))
        metrics["volume_cm3"] = round(vol / 1000, 2)
        metrics["est_pla_grams_20pct"] = round(vol / 1000 * 1.24 * 0.4, 1)

    # 5) Bed contact
    normals = mesh.face_normals
    tri_z = mesh.triangles[:, :, 2]
    areas = mesh.area_faces
    on_bed = (normals[:, 2] < -0.99) & (tri_z.max(axis=1) < BED_EPS)
    contact = float(areas[on_bed].sum())
    metrics["bed_contact_mm2"] = round(contact, 1)
    if contact < MIN_BED_CONTACT_MM2:
        errors.append(
            f"Tabla temas alanı çok küçük ({contact:.1f} mm²). Modelin altında düz bir taban yüzeyi olmalı (Z=0)."
        )
    elif contact < 0.05 * ext[0] * ext[1] and contact < 200:
        warnings.append(f"Tabla temas alanı küçük ({contact:.0f} mm²); baskı sırasında devrilebilir, brim gerekebilir.")

    # 6) Overhangs (> 45° from vertical, excluding bed faces)
    limit = -math.cos(math.radians(MAX_OVERHANG_DEG))
    overhang = (normals[:, 2] < limit - 1e-3) & ~on_bed
    oh_area = float(areas[overhang].sum())
    total_area = float(areas.sum())
    metrics["overhang_area_mm2"] = round(oh_area, 1)
    metrics["overhang_percent"] = round(100 * oh_area / total_area, 2) if total_area else 0.0
    if oh_area > 150 and oh_area / total_area > 0.04:
        warnings.append(
            f"{MAX_OVERHANG_DEG:.0f}°'den dik çıkıntı alanı {oh_area:.0f} mm² (%{100*oh_area/total_area:.1f}); "
            "destek (support) gerekebilir. Yatay tavanları 45° pah/eğimle değiştir veya parçayı döndür."
        )

    # 7) Wall thickness
    wt = _wall_thickness(mesh) if mesh.is_watertight else {"available": False}
    metrics["wall"] = wt
    if wt.get("available"):
        if wt["thin_fraction"] > 0.25:
            errors.append(
                f"Yüzeyin %{100*wt['thin_fraction']:.0f}'inde duvar kalınlığı {MIN_WALL_MM} mm'den ince "
                f"(en ince ≈ {wt['min_mm']:.2f} mm). Duvarları en az 2 mm yap."
            )
        elif wt["thin_fraction"] > 0.03:
            warnings.append(
                f"Yüzeyin %{100*wt['thin_fraction']:.0f}'inde {MIN_WALL_MM} mm'den ince bölgeler var "
                f"(en ince ≈ {wt['min_mm']:.2f} mm)."
            )

    return {"errors": errors, "warnings": warnings, "metrics": metrics}
