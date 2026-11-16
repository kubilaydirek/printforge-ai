"""Static policy check + isolated subprocess execution for LLM-generated CAD code.

This is a best-effort guard for a local, single-user tool: generated code may only import
CAD/math modules, may not touch files, processes or the network, and runs in a separate
process with a timeout and CPU limit.
"""

import ast
import json
import os
import resource
import subprocess
import sys
from pathlib import Path

from ..config import EXEC_TIMEOUT_S

RUNNER = Path(__file__).with_name("runner.py")

ALLOWED_IMPORTS = {"build123d", "math", "numpy", "typing", "itertools", "functools", "copy", "dataclasses"}
BANNED_NAMES = {
    "open", "exec", "eval", "compile", "__import__", "globals", "locals", "vars", "input",
    "breakpoint", "exit", "quit", "help", "memoryview", "setattr", "delattr", "getattr",
}


def check_policy(code: str) -> list[str]:
    try:
        tree = ast.parse(code, filename="design.py")
    except SyntaxError as e:
        return [f"Sözdizimi hatası (satır {e.lineno}): {e.msg} -> {(e.text or '').strip()}"]

    problems: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] not in ALLOWED_IMPORTS:
                    problems.append(f"Satır {node.lineno}: izin verilmeyen import '{alias.name}'")
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] not in ALLOWED_IMPORTS:
                problems.append(f"Satır {node.lineno}: izin verilmeyen import '{node.module}'")
        elif isinstance(node, ast.Name) and node.id in BANNED_NAMES:
            problems.append(f"Satır {node.lineno}: '{node.id}' kullanımı yasak")
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            problems.append(f"Satır {node.lineno}: dunder öznitelik erişimi yasak ('{node.attr}')")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id.startswith("export_"):
            problems.append(f"Satır {node.lineno}: dosya dışa aktarımı yapma, sadece `result` değişkenini ata")
    return problems


def _limit_resources() -> None:
    cpu = EXEC_TIMEOUT_S + 5
    resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
    os.setsid()


def execute(code: str, work_dir: Path) -> dict:
    """Run code in a subprocess. Returns runner info dict (ok/error, bbox, volume...)."""
    work_dir.mkdir(parents=True, exist_ok=True)
    code_path = work_dir / "design.py"
    code_path.write_text(code, encoding="utf-8")

    env = {"PATH": "/usr/bin:/bin", "HOME": str(work_dir), "PYTHONDONTWRITEBYTECODE": "1", "MPLBACKEND": "Agg"}
    try:
        proc = subprocess.run(
            [sys.executable, "-I", str(RUNNER), str(code_path), str(work_dir)],
            cwd=work_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=EXEC_TIMEOUT_S,
            preexec_fn=_limit_resources,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error_type": "Timeout", "error": f"Kod {EXEC_TIMEOUT_S} saniyede tamamlanmadı (çok karmaşık işlem veya sonsuz döngü)."}

    for line in reversed(proc.stdout.splitlines()):
        if line.startswith("RESULT:"):
            return json.loads(line[len("RESULT:"):])
    return {
        "ok": False,
        "error_type": "Crash",
        "error": f"Çalıştırıcı süreç beklenmedik şekilde sonlandı (kod {proc.returncode}).",
        "traceback": (proc.stderr or "")[-3000:],
    }
