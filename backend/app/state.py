import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import JOBS_DIR


@dataclass
class DesignSession:
    """Persists across chat turns so the user can revise the current model."""

    id: str
    requests: list[str] = field(default_factory=list)
    plan: dict | None = None
    code: str | None = None
    metrics: dict | None = None
    last_job_id: str | None = None


@dataclass
class Job:
    id: str
    session_id: str
    prompt: str
    reference_images: list[Path] = field(default_factory=list)
    status: str = "running"  # running | done | error
    events: list[dict] = field(default_factory=list)
    result: dict | None = None
    created_at: float = field(default_factory=time.time)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def dir(self) -> Path:
        d = JOBS_DIR / self.id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def url(self, path: Path) -> str:
        return f"/files/jobs/{self.id}/{path.relative_to(self.dir).as_posix()}"

    def emit(self, type_: str, **data: Any) -> None:
        with self._lock:
            self.events.append({"seq": len(self.events), "type": type_, "ts": time.time(), **data})

    def events_after(self, seq: int) -> list[dict]:
        with self._lock:
            return self.events[seq + 1 :]


@dataclass
class WorkflowState:
    """Shared blackboard the four agents read from and write to during one job."""

    request: str
    history: list[str]
    reference_images: list[Path] = field(default_factory=list)
    previous_plan: dict | None = None
    previous_code: str | None = None
    plan: dict | None = None
    code: str | None = None
    validation: dict | None = None
    inspection: dict | None = None
    revision: int = 0
    attempt_log: list[dict] = field(default_factory=list)
    best: dict | None = None


class Store:
    def __init__(self) -> None:
        self.sessions: dict[str, DesignSession] = {}
        self.jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def get_or_create_session(self, session_id: str | None) -> DesignSession:
        with self._lock:
            if session_id and session_id in self.sessions:
                return self.sessions[session_id]
            s = DesignSession(id=session_id or uuid.uuid4().hex[:12])
            self.sessions[s.id] = s
            return s

    def create_job(self, session: DesignSession, prompt: str, reference_images: list[Path] | None = None) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], session_id=session.id, prompt=prompt,
                 reference_images=reference_images or [])
        with self._lock:
            self.jobs[job.id] = job
        return job


store = Store()
