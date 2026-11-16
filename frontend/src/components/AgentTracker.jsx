import { useState } from "react";
import { AGENTS, AGENT_BY_ID } from "../jobState.js";

const STATUS_LABEL = {
  idle: "bekliyor",
  running: "çalışıyor",
  done: "tamam",
  failed: "hata → düzeltme",
  rejected: "revizyon istedi",
  error: "durdu",
};

function Pipeline({ job }) {
  return (
    <div className="pipeline">
      {AGENTS.map((a, i) => {
        const st = job.agents[a.id]?.status || "idle";
        return (
          <div key={a.id} className="pipe-step-wrap">
            <div className={`pipe-step ${st}`} style={{ "--agent": a.color }} title={job.agents[a.id]?.message}>
              <span className="pipe-no">{a.no}</span>
              <span className="pipe-name">{a.short}</span>
              <span className="pipe-status">{STATUS_LABEL[st] || st}</span>
            </div>
            {i < AGENTS.length - 1 && <span className="pipe-arrow">→</span>}
          </div>
        );
      })}
    </div>
  );
}

function Thumbs({ images, onOpenImage }) {
  return (
    <div className="thumbs">
      {images.map((im) => (
        <button key={im.url} className="thumb" onClick={() => onOpenImage(im)} title={im.label}>
          <img src={im.url} alt={im.label} loading="lazy" />
          <span>{im.label.split(" ")[0]}</span>
        </button>
      ))}
    </div>
  );
}

function Inspection({ ev }) {
  return (
    <div className={`verdict ${ev.approved ? "ok" : "bad"}`}>
      <div className="verdict-head">
        <strong>{ev.approved ? "✓ Görsel denetim onayı" : "✗ Görsel denetim: revizyon gerekli"}</strong>
        <span className="score">{ev.score}/10</span>
      </div>
      <p>{ev.summary_tr}</p>
      {ev.issues?.length > 0 && (
        <ul className="issues">
          {ev.issues.map((is, k) => (
            <li key={k} className={is.severity}>
              <span className="sev">{is.severity === "critical" ? "kritik" : is.severity === "major" ? "önemli" : "küçük"}</span>
              {is.description_tr}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function LogItem({ ev, onOpenImage }) {
  if (ev.type === "revision") {
    return <div className="log-divider">Revizyon turu {ev.revision}/{ev.max_revisions}</div>;
  }
  if (ev.type === "renders") {
    return (
      <div className="log-item">
        <span className="log-dot" style={{ background: AGENT_BY_ID.inspector.color }} />
        <div className="log-body">
          <div className="log-agent">4 · Kontrol fotoğrafları</div>
          <Thumbs images={ev.images} onOpenImage={onOpenImage} />
        </div>
      </div>
    );
  }
  if (ev.type === "inspection") {
    return (
      <div className="log-item">
        <span className="log-dot" style={{ background: AGENT_BY_ID.inspector.color }} />
        <div className="log-body">
          <Inspection ev={ev} />
        </div>
      </div>
    );
  }
  const a = AGENT_BY_ID[ev.agent];
  return (
    <div className={`log-item ${ev.status}`}>
      <span className={`log-dot ${ev.status === "running" ? "pulse" : ""}`} style={{ background: a.color }} />
      <div className="log-body">
        <div className="log-agent">
          {a.no} · {a.name}
          {ev.status !== "running" && <em className={`tag ${ev.status}`}>{STATUS_LABEL[ev.status]}</em>}
        </div>
        <div className="log-msg">{ev.message}</div>
        {ev.errors?.length > 0 && (
          <ul className="err-list">
            {ev.errors.map((e, k) => (
              <li key={k}>{e}</li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function PlanView({ plan }) {
  const d = plan.overall_dimensions_mm;
  return (
    <div className="plan">
      <p>{plan.summary_tr}</p>
      <div className="kv">
        <span>Toplam ölçü</span><b>{d.x} × {d.y} × {d.z} mm</b>
        <span>Baskı yönü</span><b>{plan.print_orientation}</b>
        <span>Malzeme</span><b>{plan.material_suggestion}</b>
      </div>
      <table>
        <thead>
          <tr><th>Bileşen</th><th>Görev</th><th>Ölçü (mm)</th><th>Konum (mm)</th></tr>
        </thead>
        <tbody>
          {plan.components.map((c) => (
            <tr key={c.name}>
              <td><code>{c.name}</code></td>
              <td>{c.role}</td>
              <td>{c.bbox_mm.x}×{c.bbox_mm.y}×{c.bbox_mm.z}</td>
              <td>{c.position_mm.x}, {c.position_mm.y}, {c.position_mm.z}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {plan.assumptions?.length > 0 && (
        <>
          <h5>Varsayımlar</h5>
          <ul>{plan.assumptions.map((x, i) => <li key={i}>{x}</li>)}</ul>
        </>
      )}
    </div>
  );
}

export default function AgentTracker({ job, onOpenImage }) {
  const [tab, setTab] = useState(null);
  const lastCode = job.codes[job.codes.length - 1];
  const running = job.status === "running";
  const r = job.result;

  return (
    <div className={`job-card ${job.status}`}>
      <div className="job-head">
        <span className="job-title">
          {running && <span className="spinner small" />}
          {job.plan?.title_tr || (job.isRevision ? "Revizyon" : "Yeni tasarım")}
        </span>
        <span className="job-rev">
          {running ? `Görsel revizyon ${job.revision}/${job.maxRevisions}` : job.status === "done" ? "Tamamlandı" : "Hata"}
        </span>
      </div>

      {job.referenceImages?.length > 0 && (
        <div className="thumbs reference-thumbs">
          {job.referenceImages.map((url, i) => (
            <button key={url} className="thumb" onClick={() => onOpenImage({ url, label: `Referans görsel ${i + 1}` })} title="Referans ürün görseli">
              <img src={url} alt={`Referans görsel ${i + 1}`} loading="lazy" />
              <span>Referans</span>
            </button>
          ))}
        </div>
      )}

      <Pipeline job={job} />

      <div className="log">
        {job.log.map((ev, i) => {
          // a "running" line is superseded once the same agent reports again
          const superseded = ev.type === "agent" && ev.status === "running" &&
            job.log.slice(i + 1).some((n) => n.type === "agent" && n.agent === ev.agent);
          return superseded ? null : <LogItem key={i} ev={ev} onOpenImage={onOpenImage} />;
        })}
      </div>

      {job.error && <div className="banner error">{job.error}</div>}

      {r && (
        <div className={`final ${r.approved ? "ok" : "warn"}`}>
          <strong>{r.approved ? "Baskıya hazır STL üretildi" : "STL üretildi (görsel denetim tam onay vermedi)"}</strong>
          <span>
            {r.metrics.size_mm.x} × {r.metrics.size_mm.y} × {r.metrics.size_mm.z} mm
            {r.metrics.volume_cm3 != null && ` · ${r.metrics.volume_cm3} cm³ · ≈${r.metrics.est_pla_grams_20pct} g PLA`}
          </span>
          {r.warnings?.length > 0 && (
            <ul className="warn-list">{r.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
          )}
          <a className="primary-btn" href={r.download_url} download>⬇ STL İndir</a>
        </div>
      )}

      {(job.plan || lastCode) && (
        <div className="tabs">
          {job.plan && (
            <button className={tab === "plan" ? "active" : ""} onClick={() => setTab(tab === "plan" ? null : "plan")}>
              Teknik plan (JSON)
            </button>
          )}
          {lastCode && (
            <button className={tab === "code" ? "active" : ""} onClick={() => setTab(tab === "code" ? null : "code")}>
              build123d kodu ({job.codes.length} sürüm)
            </button>
          )}
        </div>
      )}
      {tab === "plan" && job.plan && <PlanView plan={job.plan} />}
      {tab === "code" && lastCode && <pre className="code">{lastCode.code}</pre>}
    </div>
  );
}
