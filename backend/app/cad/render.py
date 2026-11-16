"""Headless 4-view rendering (front, side, top, isometric) with matplotlib's Agg backend."""

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import trimesh  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: E402

VIEWS = [
    ("front", "Ön (−Y yönünden)", 0, -90),
    ("side", "Yan (+X yönünden)", 0, 0),
    ("top", "Üst (+Z yönünden)", 90, -90),
    ("iso", "İzometrik", 28, -55),
]
MAX_RENDER_FACES = 70000
BASE_COLOR = np.array([0.98, 0.55, 0.18])


def _camera_dir(elev: float, azim: float) -> np.ndarray:
    e, a = math.radians(elev), math.radians(azim)
    return np.array([math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e)])


def _shade(normals: np.ndarray, elev: float, azim: float) -> np.ndarray:
    cam = _camera_dir(elev, azim)
    key = cam + np.array([0.3, -0.2, 0.6])
    key /= np.linalg.norm(key)
    diffuse = np.clip(normals @ key, 0, 1)
    rim = np.clip(normals @ cam, 0, 1) ** 2
    intensity = 0.28 + 0.55 * diffuse + 0.22 * rim
    rgb = np.clip(BASE_COLOR[None, :] * intensity[:, None], 0, 1)
    return np.concatenate([rgb, np.ones((len(rgb), 1))], axis=1)


def _render_triangles(mesh: trimesh.Trimesh, extent: float) -> tuple[np.ndarray, np.ndarray]:
    """Split long triangles so matplotlib's per-face depth sort stays correct."""
    for divisor in (40, 28, 18, 10):
        v, f, idx = trimesh.remesh.subdivide_to_size(
            mesh.vertices, mesh.faces, max_edge=max(extent / divisor, 0.5), max_iter=8, return_index=True)
        if len(f) <= MAX_RENDER_FACES:
            return v[f], mesh.face_normals[idx]
    return mesh.triangles, mesh.face_normals


def render_views(stl_path: Path, out_dir: Path, title: str = "") -> list[dict]:
    mesh = trimesh.load_mesh(str(stl_path), process=True)
    lo, hi = mesh.bounds
    tris, normals = _render_triangles(mesh, float((hi - lo).max()))
    size = hi - lo
    center = (lo + hi) / 2
    half = max(size.max() * 0.6, 5.0)
    pad = max(size[:2].max() * 0.15, 5.0)

    out = []
    for key, label, elev, azim in VIEWS:
        fig = plt.figure(figsize=(7.2, 7.2), dpi=100, facecolor="#15171c")
        ax = fig.add_subplot(111, projection="3d", facecolor="#15171c")
        ax.set_proj_type("ortho")
        ax.view_init(elev=elev, azim=azim)

        bed = np.array([
            [lo[0] - pad, lo[1] - pad, 0], [hi[0] + pad, lo[1] - pad, 0],
            [hi[0] + pad, hi[1] + pad, 0], [lo[0] - pad, hi[1] + pad, 0],
        ])
        ax.add_collection3d(Poly3DCollection([bed], facecolors=(0.35, 0.4, 0.5, 0.35), edgecolors=(0.5, 0.6, 0.75, 0.8), linewidths=0.8))

        colors = _shade(normals, elev, azim)
        coll = Poly3DCollection(tris, facecolors=colors, edgecolors=colors, linewidths=0.3)
        ax.add_collection3d(coll)

        ax.set_xlim(center[0] - half, center[0] + half)
        ax.set_ylim(center[1] - half, center[1] + half)
        ax.set_zlim(max(center[2] - half, -pad), center[2] + half)
        ax.set_box_aspect((1, 1, 1), zoom=1.45)
        ax.set_axis_off()
        fig.subplots_adjust(0, 0, 1, 1)
        fig.text(0.03, 0.96, label, color="#e6e9ef", fontsize=13, weight="bold", va="top")
        fig.text(0.03, 0.915, f"X {size[0]:.1f}  Y {size[1]:.1f}  Z {size[2]:.1f} mm", color="#9aa3b2", fontsize=10, va="top")
        if title:
            fig.text(0.97, 0.96, title[:40], color="#9aa3b2", fontsize=10, ha="right", va="top")

        path = out_dir / f"view_{key}.png"
        fig.savefig(path, facecolor=fig.get_facecolor())
        plt.close(fig)
        out.append({"view": key, "label": label, "path": path})
    return out
