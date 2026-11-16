import { useCallback, useEffect, useRef, useState } from "react";
import { getHealth, startGeneration, subscribeToJob } from "./api.js";
import { applyEvent, initialJob } from "./jobState.js";
import ChatPanel from "./components/ChatPanel.jsx";
import Viewer3D from "./components/Viewer3D.jsx";
import ApiKeyGate from "./components/ApiKeyGate.jsx";

export default function App() {
  const [health, setHealth] = useState(null);
  const [healthError, setHealthError] = useState(null);
  const [sessionId, setSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [jobs, setJobs] = useState({});
  const [activeJobId, setActiveJobId] = useState(null);
  const [lightbox, setLightbox] = useState(null);
  const unsubscribers = useRef([]);

  const refreshHealth = useCallback(() => {
    getHealth().then(setHealth).catch((e) => setHealthError(e.message));
  }, []);

  useEffect(() => {
    refreshHealth();
    return () => unsubscribers.current.forEach((u) => u());
  }, [refreshHealth]);

  useEffect(() => {
    if (!lightbox) return;
    const onKey = (e) => e.key === "Escape" && setLightbox(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [lightbox]);

  const busy = activeJobId != null && jobs[activeJobId]?.status === "running";

  const send = useCallback(
    async (prompt, images = []) => {
      const imageUrls = images.map((f) => URL.createObjectURL(f));
      setMessages((m) => [...m, { role: "user", text: prompt, images: imageUrls, id: crypto.randomUUID() }]);
      try {
        const { job_id, session_id, is_revision } = await startGeneration(prompt, sessionId, images);
        setSessionId(session_id);
        setJobs((j) => ({ ...j, [job_id]: initialJob(job_id, prompt, is_revision) }));
        setMessages((m) => [...m, { role: "job", jobId: job_id, id: job_id }]);
        setActiveJobId(job_id);
        const unsub = subscribeToJob(job_id, (ev) =>
          setJobs((j) => ({ ...j, [job_id]: applyEvent(j[job_id], ev) }))
        );
        unsubscribers.current.push(unsub);
      } catch (e) {
        setMessages((m) => [...m, { role: "system", text: e.message, id: crypto.randomUUID() }]);
      }
    },
    [sessionId]
  );

  const newDesign = () => {
    setSessionId(null);
    setMessages([]);
    setActiveJobId(null);
  };

  // Latest finished model wins; otherwise show the live preview of the running job.
  const ordered = messages.filter((m) => m.role === "job").map((m) => jobs[m.jobId]).filter(Boolean);
  const activeJob = activeJobId ? jobs[activeJobId] : null;
  const lastFinal = [...ordered].reverse().find((j) => j.result);
  let viewerModel = null;
  if (activeJob?.status === "running" && activeJob.model) {
    viewerModel = { url: activeJob.model.stl_url, metrics: activeJob.model.metrics, live: true, title: activeJob.plan?.title_tr };
  } else if (lastFinal) {
    const r = lastFinal.result;
    viewerModel = { url: r.stl_url, metrics: r.metrics, live: false, title: r.title, downloadUrl: r.download_url, result: r };
  }

  if (health && !health.llm_ready) {
    return <ApiKeyGate detail={health.llm_detail} onReady={refreshHealth} onRetry={refreshHealth} />;
  }

  return (
    <div className="app">
      <ChatPanel
        messages={messages}
        jobs={jobs}
        busy={busy}
        hasModel={Boolean(lastFinal)}
        onSend={send}
        onNewDesign={newDesign}
        onOpenImage={setLightbox}
        health={health}
        healthError={healthError}
      />
      <Viewer3D model={viewerModel} running={busy} runningJob={activeJob} />
      {lightbox && (
        <div className="lightbox" onClick={() => setLightbox(null)}>
          <figure>
            <img src={lightbox.url} alt={lightbox.label} />
            <figcaption>{lightbox.label} · kapatmak için tıklayın</figcaption>
          </figure>
        </div>
      )}
    </div>
  );
}
