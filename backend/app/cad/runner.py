"""Executed in an isolated subprocess: runs generated build123d code and exports STL files.

Usage: python -I runner.py <design.py> <out_dir>
Prints a single JSON line prefixed with RESULT: on stdout.
"""

import json
import math
import sys
import traceback

from build123d import *  # noqa: F401,F403
from build123d import Compound, Part, Shape, Solid, chamfer, export_stl, fillet


def _valid(shape) -> bool:
    v = shape.is_valid
    return bool(v() if callable(v) else v)


def safe_fillet(part, edges, radius):
    """Fillet that returns the original part instead of failing."""
    try:
        edges = list(edges)
        if not edges or radius <= 0:
            return part
        out = fillet(edges, radius)
        return out if _valid(out) else part
    except Exception:
        return part


def safe_chamfer(part, edges, length):
    try:
        edges = list(edges)
        if not edges or length <= 0:
            return part
        out = chamfer(edges, length)
        return out if _valid(out) else part
    except Exception:
        return part


def _to_shape(obj):
    if hasattr(obj, "part") and obj.part is not None and not isinstance(obj, Shape):
        obj = obj.part  # BuildPart context
    if isinstance(obj, (list, tuple)):
        obj = Compound(children=[_to_shape(o) for o in obj])
    if not isinstance(obj, Shape):
        raise TypeError(f"`result` bir build123d Part/Solid olmalı, gelen tür: {type(obj).__name__}")
    return obj


def main() -> None:
    code_path, out_dir = sys.argv[1], sys.argv[2]
    src = open(code_path, encoding="utf-8").read()
    ns = {"__name__": "__design__", "math": math, "safe_fillet": safe_fillet, "safe_chamfer": safe_chamfer}
    exec("from build123d import *", ns)
    try:
        exec(compile(src, "design.py", "exec"), ns)
        if "result" not in ns:
            raise NameError("Kod sonunda `result` değişkeni tanımlanmadı (result = <son parça>).")
        shape = _to_shape(ns["result"])
        solids = shape.solids()
        if len(solids) == 0:
            raise ValueError("`result` içinde katı (solid) yok. 2D bir çizim extrude edilmemiş olabilir.")
        bb = shape.bounding_box()
        # coarse first: OCC caches triangulation on the shape and only refines it later
        export_stl(shape, f"{out_dir}/preview.stl", tolerance=0.25, angular_tolerance=0.4)
        export_stl(shape, f"{out_dir}/model.stl", tolerance=0.02, angular_tolerance=0.15)
        info = {
            "ok": True,
            "solid_count": len(solids),
            "volume_mm3": float(shape.volume),
            "is_valid": _valid(shape),
            "bbox_min": [bb.min.X, bb.min.Y, bb.min.Z],
            "bbox_max": [bb.max.X, bb.max.Y, bb.max.Z],
        }
    except Exception as e:  # report everything back to the coder agent
        tb = traceback.extract_tb(e.__traceback__)
        design_frames = [f for f in tb if f.filename == "design.py"]
        line = design_frames[-1].lineno if design_frames else None
        info = {
            "ok": False,
            "error_type": type(e).__name__,
            "error": str(e)[:1500],
            "line": line,
            "traceback": "".join(traceback.format_exception(type(e), e, e.__traceback__))[-3000:],
        }
    print("RESULT:" + json.dumps(info))


if __name__ == "__main__":
    main()
