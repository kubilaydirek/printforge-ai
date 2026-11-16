import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# "subscription": uses the locally logged-in `claude` CLI (Claude Pro/Max plan, no API credits)
# "api": uses ANTHROPIC_API_KEY with pay-as-you-go API credits
LLM_BACKEND = os.getenv("LLM_BACKEND", "subscription").strip().lower()
CLAUDE_CLI_MODEL = os.getenv("CLAUDE_CLI_MODEL", "").strip()  # empty = the plan's default model
CLI_TIMEOUT_S = int(os.getenv("CLI_TIMEOUT_S", "900"))

MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")
EFFORT_PLANNER = os.getenv("EFFORT_PLANNER", "medium")
EFFORT_CODER = os.getenv("EFFORT_CODER", "high")
EFFORT_INSPECTOR = os.getenv("EFFORT_INSPECTOR", "medium")

DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data")).resolve()
JOBS_DIR = DATA_DIR / "jobs"
FRONTEND_DIST = (BASE_DIR.parent / "frontend" / "dist").resolve()

# Creality Ender 5 S1 build volume (mm)
BED_X = 220.0
BED_Y = 220.0
BED_Z = 280.0

MIN_WALL_MM = 1.5
MAX_OVERHANG_DEG = 45.0
MIN_BED_CONTACT_MM2 = 10.0

MAX_VISUAL_REVISIONS = int(os.getenv("MAX_VISUAL_REVISIONS", "3"))
MAX_FIX_ATTEMPTS = int(os.getenv("MAX_FIX_ATTEMPTS", "4"))
EXEC_TIMEOUT_S = int(os.getenv("EXEC_TIMEOUT_S", "120"))

# Reference product photos uploaded by the user (Planner + Inspector read these)
MAX_REFERENCE_IMAGES = int(os.getenv("MAX_REFERENCE_IMAGES", "4"))
MAX_IMAGE_MB = int(os.getenv("MAX_IMAGE_MB", "12"))
ALLOWED_IMAGE_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}

JOBS_DIR.mkdir(parents=True, exist_ok=True)

ENV_PATH = BASE_DIR / ".env"


def set_api_key(key: str) -> None:
    """Switches this process to API-key mode and persists the key to backend/.env,
    so the web UI's one-time key prompt survives a server restart."""
    global LLM_BACKEND, MODEL
    key = key.strip()
    os.environ["ANTHROPIC_API_KEY"] = key
    os.environ["LLM_BACKEND"] = "api"
    LLM_BACKEND = "api"
    MODEL = os.getenv("CLAUDE_MODEL", MODEL)

    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    seen = {"ANTHROPIC_API_KEY": False, "LLM_BACKEND": False}
    for i, line in enumerate(lines):
        for name in seen:
            if line.strip().startswith(f"{name}="):
                lines[i] = f"{name}={key if name == 'ANTHROPIC_API_KEY' else 'api'}"
                seen[name] = True
    if not seen["LLM_BACKEND"]:
        lines.append("LLM_BACKEND=api")
    if not seen["ANTHROPIC_API_KEY"]:
        lines.append(f"ANTHROPIC_API_KEY={key}")
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
