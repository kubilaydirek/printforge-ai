export async function getHealth() {
  const r = await fetch("/api/health");
  if (!r.ok) throw new Error("Sunucuya ulaşılamadı");
  return r.json();
}

export async function setApiKey(apiKey) {
  const r = await fetch("/api/api-key", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ api_key: apiKey }),
  });
  if (!r.ok) {
    let detail = "";
    try {
      detail = (await r.json()).detail || "";
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail || `İstek başarısız (${r.status})`);
  }
  return r.json();
}

export async function startGeneration(prompt, sessionId, images = []) {
  const form = new FormData();
  form.set("prompt", prompt);
  if (sessionId) form.set("session_id", sessionId);
  for (const file of images) form.append("images", file);

  const r = await fetch("/api/generate", { method: "POST", body: form });
  if (!r.ok) {
    let detail = "";
    try {
      detail = (await r.json()).detail || "";
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail || `İstek başarısız (${r.status})`);
  }
  return r.json();
}

/** Subscribes to a job's live event stream; reconnects from the last seen event. */
export function subscribeToJob(jobId, onEvent) {
  let lastSeq = -1;
  let source = null;
  let closed = false;
  let retryTimer = null;

  const open = () => {
    source = new EventSource(`/api/jobs/${jobId}/events?after=${lastSeq}`);
    source.onmessage = (msg) => {
      const ev = JSON.parse(msg.data);
      if (ev.seq <= lastSeq) return;
      lastSeq = ev.seq;
      onEvent(ev);
      if (ev.type === "done") close();
    };
    source.onerror = () => {
      source.close();
      if (!closed) retryTimer = setTimeout(open, 1500);
    };
  };

  const close = () => {
    closed = true;
    clearTimeout(retryTimer);
    source?.close();
  };

  open();
  return close;
}
