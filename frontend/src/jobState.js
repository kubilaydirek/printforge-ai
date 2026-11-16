export const AGENTS = [
  { id: "planner", no: 1, name: "Mimari Planlayıcı", short: "Planlayıcı", color: "#60a5fa" },
  { id: "coder", no: 2, name: "CAD Mühendisi", short: "CAD Mühendisi", color: "#a78bfa" },
  { id: "validator", no: 3, name: "Kod & Geometri Denetçisi", short: "Denetçi", color: "#34d399" },
  { id: "inspector", no: 4, name: "Görsel Denetçi (VLM)", short: "Görsel Denetçi", color: "#f472b6" },
];

export const AGENT_BY_ID = Object.fromEntries(AGENTS.map((a) => [a.id, a]));

export function initialJob(jobId, prompt, isRevision) {
  return {
    jobId,
    prompt,
    isRevision,
    status: "running",
    agents: Object.fromEntries(AGENTS.map((a) => [a.id, { status: "idle", message: "" }])),
    log: [],
    referenceImages: [],
    plan: null,
    codes: [],
    validations: [],
    renders: [],
    inspections: [],
    revision: 0,
    maxRevisions: 3,
    model: null,
    result: null,
    error: null,
  };
}

export function applyEvent(job, ev) {
  const next = { ...job };
  switch (ev.type) {
    case "reference_images":
      next.referenceImages = ev.images;
      break;
    case "agent":
      next.agents = { ...job.agents, [ev.agent]: { status: ev.status, message: ev.message } };
      next.log = [...job.log, ev];
      break;
    case "plan":
      next.plan = ev.plan;
      break;
    case "revision":
      next.revision = ev.revision;
      next.maxRevisions = ev.max_revisions;
      if (ev.revision > 0) next.log = [...job.log, ev];
      break;
    case "code":
      next.codes = [...job.codes, ev];
      break;
    case "validation":
      next.validations = [...job.validations, ev];
      break;
    case "renders":
      next.renders = [...job.renders, ev];
      next.log = [...job.log, ev];
      break;
    case "inspection":
      next.inspections = [...job.inspections, ev];
      next.log = [...job.log, ev];
      break;
    case "model":
      next.model = ev;
      break;
    case "result":
      next.result = ev;
      break;
    case "error":
      next.error = ev.message;
      next.agents = Object.fromEntries(
        Object.entries(job.agents).map(([k, a]) => [k, a.status === "running" ? { ...a, status: "error" } : a])
      );
      break;
    case "done":
      next.status = ev.status;
      break;
    default:
      break;
  }
  return next;
}
