"""Multi-agent workflow: Planner -> (Coder <-> Validator) -> Inspector -> (revise | deliver)."""

import logging
import shutil
from pathlib import Path

from .agents import cad_coder, inspector, planner, validator
from .cad.render import render_views
from .config import MAX_FIX_ATTEMPTS, MAX_VISUAL_REVISIONS
from .llm import LLMError
from .state import DesignSession, Job, WorkflowState

log = logging.getLogger("printforge")


class WorkflowFailed(RuntimeError):
    pass


def _agent(job: Job, agent: str, status: str, message: str, **extra) -> None:
    job.emit("agent", agent=agent, status=status, message=message, **extra)


def _build_valid_model(job: Job, state: WorkflowState, feedback: dict | None) -> dict | None:
    """Agent 2 <-> Agent 3 loop. Returns a passing validation report, or None."""
    errors: list[str] | None = None
    tb: str | None = None
    max_bodies = int((state.plan or {}).get("max_bodies") or 1)

    for attempt in range(MAX_FIX_ATTEMPTS):
        if errors:
            msg = f"Denetçinin bulduğu {len(errors)} hata düzeltiliyor (deneme {attempt + 1}/{MAX_FIX_ATTEMPTS})..."
        elif feedback:
            msg = "Görsel denetçinin notlarına göre model revize ediliyor..."
        else:
            msg = "Plan build123d koduna dönüştürülüyor..."
        _agent(job, "coder", "running", msg, revision=state.revision, attempt=attempt)

        out = cad_coder.run(state, errors=errors, traceback=tb, visual_feedback=feedback)
        state.code = out["code"]
        job.emit("code", revision=state.revision, attempt=attempt, code=out["code"],
                 approach=out.get("approach_tr", ""), changes=out.get("changes_tr", []))
        _agent(job, "coder", "done", out.get("approach_tr") or "Kod yazıldı.", revision=state.revision, attempt=attempt)

        _agent(job, "validator", "running", "Kod izole ortamda çalıştırılıyor, STL üretiliyor ve geometri denetleniyor...",
               revision=state.revision, attempt=attempt)
        report = validator.run(state.code, job.dir / f"r{state.revision}_a{attempt}", max_bodies)
        state.validation = report
        job.emit("validation", revision=state.revision, attempt=attempt, ok=report["ok"], stage=report["stage"],
                 errors=report["errors"], warnings=report["warnings"], metrics=report["metrics"])
        state.attempt_log.append({
            "revision": state.revision,
            "attempt": attempt,
            "outcome": "başarılı" if report["ok"] else "; ".join(report["errors"])[:400],
        })

        if report["ok"]:
            m = report["metrics"]
            s = m.get("size_mm", {})
            _agent(job, "validator", "done",
                   f"STL geçerli: su geçirmez, {m.get('body_count', 1)} gövde, {s.get('x')}×{s.get('y')}×{s.get('z')} mm, "
                   f"tabla teması {m.get('bed_contact_mm2')} mm².", revision=state.revision, attempt=attempt)
            job.emit("model", revision=state.revision, stl_url=job.url(Path(report["stl_path"])), metrics=m)
            return report

        _agent(job, "validator", "failed",
               f"{len(report['errors'])} sorun bulundu ({report['stage']}), CAD Mühendisine geri gönderiliyor.",
               revision=state.revision, attempt=attempt, errors=report["errors"])
        errors, tb = report["errors"], report.get("traceback")
    return None


def _run(job: Job, state: WorkflowState) -> dict:
    if state.reference_images:
        job.emit("reference_images", images=[job.url(p) for p in state.reference_images])

    # Agent 1 - Planner
    _agent(job, "planner", "running",
           ("Referans fotoğraf(lar) inceleniyor; bileşenler, gerçek ölçüler ve baskı yönü hesaplanıyor..."
            if state.reference_images else
            "İstek analiz ediliyor; bileşenler, gerçek ölçüler ve baskı yönü hesaplanıyor...") if not state.previous_plan
           else "Mevcut plan revizyon isteğine göre güncelleniyor...")
    state.plan = planner.run(state)
    job.emit("plan", plan=state.plan)
    d = state.plan.get("overall_dimensions_mm", {})
    _agent(job, "planner", "done",
           f"Plan hazır: {state.plan.get('title_tr')} — {len(state.plan.get('components', []))} bileşen, "
           f"≈{d.get('x')}×{d.get('y')}×{d.get('z')} mm.")

    feedback: dict | None = None
    for revision in range(MAX_VISUAL_REVISIONS + 1):
        state.revision = revision
        job.emit("revision", revision=revision, max_revisions=MAX_VISUAL_REVISIONS)

        report = _build_valid_model(job, state, feedback)
        if report is None:
            if state.best:
                break
            raise WorkflowFailed("CAD Mühendisi ve Denetçi, izin verilen deneme sayısında geçerli bir model üretemedi. "
                                 "İsteği biraz daha basit veya net yazarak tekrar deneyin.")

        # Agent 4 - Visual Inspector
        _agent(job, "inspector", "running", "Model 4 açıdan (Ön, Yan, Üst, İzometrik) görüntüleniyor...", revision=revision)
        render_dir = job.dir / f"r{revision}_renders"
        render_dir.mkdir(exist_ok=True)
        renders = render_views(Path(report["preview_path"]), render_dir, state.plan.get("title_tr", ""))
        job.emit("renders", revision=revision,
                 images=[{"view": r["view"], "label": r["label"], "url": job.url(r["path"])} for r in renders])

        _agent(job, "inspector", "running", "Görüntüler Claude Vision ile denetleniyor...", revision=revision)
        insp = inspector.run(state, renders, report)
        state.inspection = insp
        job.emit("inspection", revision=revision, **insp)

        candidate = {"revision": revision, "report": report, "inspection": insp, "code": state.code}
        best = state.best
        if best is None or (insp["approved"], insp["score"]) >= (best["inspection"]["approved"], best["inspection"]["score"]):
            state.best = candidate

        if insp["approved"]:
            _agent(job, "inspector", "done", f"Onaylandı (puan {insp['score']}/10): {insp['summary_tr']}", revision=revision)
            break

        serious = [i for i in insp["issues"] if i["severity"] in ("critical", "major")]
        if revision < MAX_VISUAL_REVISIONS:
            _agent(job, "inspector", "rejected",
                   f"{len(serious) or len(insp['issues'])} kusur bulundu (puan {insp['score']}/10). "
                   f"Düzeltme notları CAD Mühendisine gönderiliyor — revizyon {revision + 1}/{MAX_VISUAL_REVISIONS}.",
                   revision=revision)
            feedback = {"summary": insp["summary_tr"], "issues": insp["issues"]}
            state.code = candidate["code"]
        else:
            _agent(job, "inspector", "rejected",
                   f"Revizyon hakkı doldu. En yüksek puanlı sürüm teslim ediliyor (puan {state.best['inspection']['score']}/10).",
                   revision=revision)

    return state.best


def run_job(job: Job, session: DesignSession) -> None:
    state = WorkflowState(
        request=job.prompt,
        history=session.requests + [job.prompt],
        reference_images=job.reference_images,
        previous_plan=session.plan,
        previous_code=session.code,
    )
    try:
        best = _run(job, state)
        src = Path(best["report"]["stl_path"])
        final = job.dir / "final.stl"
        shutil.copyfile(src, final)
        (job.dir / "final_design.py").write_text(best["code"], encoding="utf-8")

        insp = best["inspection"]
        result = {
            "title": state.plan.get("title_tr"),
            "object_name": state.plan.get("object_name") or "model",
            "stl_url": job.url(final),
            "download_url": f"/api/jobs/{job.id}/download",
            "metrics": best["report"]["metrics"],
            "warnings": best["report"]["warnings"],
            "approved": insp["approved"],
            "score": insp["score"],
            "summary": insp["summary_tr"],
            "revision": best["revision"],
            "material": state.plan.get("material_suggestion"),
            "orientation": state.plan.get("print_orientation"),
        }
        job.result = result
        session.requests.append(job.prompt)
        session.plan, session.code, session.metrics, session.last_job_id = state.plan, best["code"], result["metrics"], job.id
        job.emit("result", **result)
        job.status = "done"
    except (LLMError, WorkflowFailed) as e:
        job.status = "error"
        job.emit("error", message=str(e))
    except Exception as e:
        log.exception("workflow crashed")
        job.status = "error"
        job.emit("error", message=f"Beklenmeyen hata: {type(e).__name__}: {e}")
    finally:
        job.emit("done", status=job.status)
