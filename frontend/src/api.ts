import { askAiModel } from "./aiChoice";
import { t as tr, trf, num } from "./i18n";

const TOKEN_KEY = "vvs_token";
export function getToken(): string | null { return localStorage.getItem(TOKEN_KEY); }
export function setToken(t: string | null) { if (t) localStorage.setItem(TOKEN_KEY, t); else localStorage.removeItem(TOKEN_KEY); }

/** The signed-in address, read out of the token the server issued. Display only - the server checks the token. */
export function currentEmail(): string | null {
  const t = getToken();
  if (!t) return null;
  try {
    const p = t.split(".")[1];
    const json = atob(p.replace(/-/g, "+").replace(/_/g, "/"));
    return JSON.parse(decodeURIComponent(escape(json))).email ?? null;
  } catch {
    return null;
  }
}

/** Vad servern sa om varför den sa nej. Delas av req och fetchBlob: ett fel utan innehåll ("Hämtning
 *  misslyckades") döljer sin egen orsak, och det var precis det anbudssidan visade i en vecka. */
/* Tjänstens egna besked är skrivna på svenska, och de slås upp här - på samma svenska sträng som
 * gränssnittet använder som nyckel. Det är enda stället de går genom: varje `.message` som visas i en
 * komponent kommer härifrån. Alternativet, ett Accept-Language och en andra ordbok i Python, hade flyttat
 * en presentationsfråga in i tjänsten och gett två ordböcker som glider isär.
 *
 * De 36 beskeden som är f-strängar går inte att slå upp - de bär sitt tal i sig och blir kvar på svenska. */
async function failure(res: Response): Promise<Error> {
  let msg = res.statusText || trf("Fel {0}", res.status);
  try {
    const j = await res.json();
    const d = j.detail;
    // FastAPI answers a rejected body with a list of problems rather than a sentence, and rendering that
    // straight gave the reader "[object Object]" - which says less than the status line it replaced
    msg = typeof d === "string" ? d
      : typeof d?.message === "string" ? d.message
      : Array.isArray(d) ? d.map((x: any) => x?.msg ? `${x.msg}${x.loc ? ` (${x.loc.slice(-1)})` : ""}` : JSON.stringify(x)).join("; ")
      : d ? JSON.stringify(d) : msg;
  } catch { /* a body that is not JSON leaves the status line, which is still a sentence */ }
  return new Error(`${tr(msg)} (${res.status})`);
}

async function req(path: string, init: RequestInit = {}): Promise<any> {
  const headers: Record<string, string> = { ...(init.headers as any) };
  const tok = getToken();
  if (tok) headers["Authorization"] = `Bearer ${tok}`;
  const res = await fetch(path, { ...init, headers });
  if (res.status === 401) { setToken(null); window.location.href = "/login"; throw new Error(tr("Ej inloggad")); }
  if (!res.ok) {
    throw await failure(res);
  }
  const ct = res.headers.get("content-type") || "";
  return ct.includes("application/json") ? res.json() : res;
}

const assetUrls = new Map<string, string>();

export const api = {
  login: async (email: string, password: string) => {
    const body = new URLSearchParams({ username: email, password });
    const res = await fetch("/api/auth/login", { method: "POST", body });
    if (!res.ok) throw new Error(tr((await res.json()).detail || "Inloggning misslyckades"));
    const j = await res.json(); setToken(j.access_token); return j;
  },
  register: async (email: string, password: string) => {
    const j = await req("/api/auth/register", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password }) });
    setToken(j.access_token); return j;
  },
  me: () => req("/api/auth/me"),
  knowledge: () => req("/api/knowledge"),
  projects: () => req("/api/projects"),
  createProject: (name: string, description: string, contract_form = "AB04", discipline = "vvs", tech_spec = false, abt_variant = "ritningar") =>
    req("/api/projects", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, description, contract_form, discipline, tech_spec, abt_variant }) }),
  // the disciplines the service knows, built or not: the choice shows them all and lets the built ones be chosen
  disciplines: () => req("/api/disciplines"),
  // contract form and discipline after the fact: the server refuses a change that is not confirmed
  setProjectForm: (id: string, body: { contract_form?: string; discipline?: string; tech_spec?: boolean; abt_variant?: string; confirm: boolean }) =>
    req(`/api/projects/${id}/form`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  project: (id: string) => req(`/api/projects/${id}`),
  // ABT 06: rooms read from the A-plans' room labels, counted page by page
  roomsPrice: (drawingId: string) => req(`/api/drawings/${drawingId}/rooms/price`),
  readRooms: (drawingId: string) => req(`/api/drawings/${drawingId}/rooms`, { method: "POST" }),
  projectRooms: (projectId: string) => req(`/api/projects/${projectId}/rooms`),
  chooseRoomPage: (projectId: string, body: { drawing_id: string; page: number; counted: boolean }) =>
    req(`/api/projects/${projectId}/rooms/pages`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  projectUnits: (projectId: string) => req(`/api/projects/${projectId}/units`),
  nameUnit: (projectId: string, code: string, name: string) =>
    req(`/api/projects/${projectId}/units/names`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ code, name }) }),
  projectSymbols: (projectId: string) => req(`/api/projects/${projectId}/symbols`),
  nameSymbol: (projectId: string, id: string, name: string) =>
    req(`/api/projects/${projectId}/symbols/names`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id, name }) }),
  symbolPictureUrl: (drawingId: string, id: string) => `/api/drawings/${drawingId}/symbols/${encodeURIComponent(id)}.png`,
  keyFigures: () => req(`/api/key-figures`),
  createKeyFigure: (body: any) => req(`/api/key-figures`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  updateKeyFigure: (id: string, body: any) => req(`/api/key-figures/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  deleteKeyFigure: (id: string) => req(`/api/key-figures/${id}`, { method: "DELETE" }),
  projectSchablon: (projectId: string) => req(`/api/projects/${projectId}/schablon`),
  putEstimate: (projectId: string, body: any) =>
    req(`/api/projects/${projectId}/estimate`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  deleteProject: (id: string) => req(`/api/projects/${id}`, { method: "DELETE" }),
  upload: (projectId: string, file: File) => { const fd = new FormData(); fd.append("file", file); return req(`/api/projects/${projectId}/drawings`, { method: "POST", body: fd }); },
  drawing: (id: string) => req(`/api/drawings/${id}`),
  deleteDrawing: (id: string) => req(`/api/drawings/${id}`, { method: "DELETE" }),
  /** scaleRatio: nämnaren i 1:N, för ett blad vars egen stämpel inte räckte. Utelämnad läser bladet självt. */
  /** aiModel: vilken språkmodell som läser - utelämnad frågas den som startar analysen (AiModelDialog). */
  analyze: async (drawingId: string, scaleRatio?: number, page = 0, _assignmentMode = "combined", _sourceStyle = "auto",
                  aiModel?: string) => {
    const ai_model = aiModel ?? await askAiModel();
    if (!ai_model) throw new Error("Analysen startades inte.");
    return req(`/api/drawings/${drawingId}/analyze`, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scale_ratio: scaleRatio, page, assignment_mode: "combined", source_style: "auto", ai_model }) });
  },
  analysisOptions: () => req("/api/analysis-options"),
  job: (id: string) => req(`/api/jobs/${id}`),
  // bladet läsaren står på: rören, etiketterna och bläcket hör till ett blad, och handlingens mängd följer med
  result: (id: string, page?: number) => req(`/api/jobs/${id}/result${page == null ? "" : `?page=${page}`}`),
  artifacts: (id: string) => req(`/api/jobs/${id}/artifacts`),
  why: (jobId: string, pipeId: string) => req(`/api/jobs/${jobId}/why/${pipeId}`),
  // a second opinion by eye on a finished reading; its findings never move a metre
  vision: (jobId: string, page: number) => req(`/api/jobs/${jobId}/vision?page=${page}`, { method: "POST" }),
  fileUrl: (drawingId: string) => `/api/drawings/${drawingId}/file`,
  exportUrl: (jobId: string, fmt: string) => `/api/jobs/${jobId}/export/${fmt}`,
  artifactUrl: (jobId: string, name: string) => `/api/jobs/${jobId}/artifacts/${name}`,
  film: (jobId: string) => req(`/api/jobs/${jobId}/film`),
  agent: (jobId: string, body: any) =>
    req(`/api/jobs/${jobId}/agent`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  liveSession: (jobId: string, language: "sv" | "en" = "sv") => req(`/api/jobs/${jobId}/live/session?language=${language}`, { method: "POST" }),
  liveText: (jobId: string, input: any[], previous: string | null, language: "sv" | "en" = "sv") =>
    req(`/api/jobs/${jobId}/live/text?language=${language}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ input, previous_response_id: previous }) }),
  agentTools: () => req(`/api/agent/tools`),
  // Agenten som egen plats: filerna ligger på användaren, inte på ett projekt, och frågan går till dess egna
  // verktyg. Skild från `agent(jobId, …)`, som svarar om en bestämd läsning.
  deskFiles: () => req(`/api/desk/files`),
  deskUpload: (file: File) => { const fd = new FormData(); fd.append("file", file); return req(`/api/desk/files`, { method: "POST", body: fd }); },
  deskTools: () => req(`/api/desk/tools`),
  deskAsk: (body: any) =>
    req(`/api/desk/ask`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  judge: (jobId: string) => req(`/api/jobs/${jobId}/judge`),
  agentTool: (jobId: string, name: string, args: any = {}) =>
    req(`/api/jobs/${jobId}/agent/tool`, { method: "POST", headers: { "Content-Type": "application/json" },
                                           body: JSON.stringify({ name, arguments: args }) }),
  // Accepting a change the agent proposed. The proposal itself never travels back: the call that produced it
  // does, and the server runs it again and writes what comes out - so the metres recorded are the reading's.
  agentEdit: (jobId: string, name: string, args: any = {}, note?: string) =>
    req(`/api/jobs/${jobId}/agent/edit`, { method: "POST", headers: { "Content-Type": "application/json" },
                                           body: JSON.stringify({ name, arguments: args, note }) }),
  corrections: (drawingId: string) => req(`/api/drawings/${drawingId}/corrections`),
  addCorrection: (drawingId: string, body: any) =>
    req(`/api/drawings/${drawingId}/corrections`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  undoCorrection: (drawingId: string, id: string) =>
    req(`/api/drawings/${drawingId}/corrections/${id}`, { method: "DELETE" }),
  /** Ett ritat rättelsestreck böjt i efterhand: nya punkter och metrarna de mäter. */
  reshapeCorrection: (drawingId: string, id: string, points: number[][], meters: number) =>
    req(`/api/drawings/${drawingId}/corrections/${id}/shape`, { method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ points, meters }) }),
  // "Kontrollerad mängd": bladets rättade mängd sparad som facit för de lärda reglerna
  confirmTakeoff: (jobId: string, page: number) =>
    req(`/api/jobs/${jobId}/kontrollerad`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ page }) }),
  withdrawConfirmed: (jobId: string, page: number) =>
    req(`/api/jobs/${jobId}/kontrollerad?page=${page}`, { method: "DELETE" }),
  lessons: () => req("/api/lessons"),
  rules: () => req("/api/rules"),
  settings: () => req("/api/settings"),
  setSettings: (body: any) => req("/api/settings", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  materials: (qs: string) => req(`/api/materials?${qs}`),
  // ---- teknisk beskrivning (backend/app/tech_spec.py) ----
  techSpecs: (projectId: string, source: "tb" | "ifc" = "tb") => req(`/api/projects/${projectId}/tech-specs?source=${source}`),
  // en IFC-modell (.ifc eller .zip) läst till VVS-material: samma poster och matchning som en teknisk beskrivning
  // en materiallista: mejl (.eml), text, Word, Excel, CSV/BOM - eller text inklistrad ur ett mejl
  uploadMaterialList: (projectId: string, file: File) => { const fd = new FormData(); fd.append("file", file); return req(`/api/projects/${projectId}/material-list`, { method: "POST", body: fd }); },
  materialListText: (projectId: string, text: string, title = "") =>
    req(`/api/projects/${projectId}/material-list/text`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text, title }) }),
  uploadIfc: (projectId: string, file: File) => { const fd = new FormData(); fd.append("file", file); return req(`/api/projects/${projectId}/ifc`, { method: "POST", body: fd }); },
  uploadTechSpec: (projectId: string, file: File) => { const fd = new FormData(); fd.append("file", file); return req(`/api/projects/${projectId}/tech-specs`, { method: "POST", body: fd }); },
  techSpec: (id: string) => req(`/api/tech-specs/${id}`),
  deleteTechSpec: (id: string) => req(`/api/tech-specs/${id}`, { method: "DELETE" }),
  // AI-kontrollen: missat och val i katalogen, billigt och ur den gemensamma budgeten
  // det egna varumärkets sortiment (Alterna) och likvärdighetsförslagen ur det
  brandCatalog: () => req("/api/brand-catalog"),
  brandImport: (url = "") => req("/api/brand-catalog/import", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url }) }),
  brandUpload: (file: File) => { const fd = new FormData(); fd.append("file", file); return req("/api/brand-catalog/upload", { method: "POST", body: fd }); },
  setItemQuantity: (specId: string, itemId: string, quantity: number | null) =>
    req(`/api/tech-specs/${specId}/items/${itemId}/quantity`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ quantity }) }),
  techSpecAi: (id: string) => req(`/api/tech-specs/${id}/ai`, { method: "POST" }),
  techSpecMissed: (id: string, key: string, accept: boolean) =>
    req(`/api/tech-specs/${id}/ai/missed/${key}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ accept }) }),
  techSpecMail: (id: string, body: { ids?: string[]; to?: string }) =>
    req(`/api/tech-specs/${id}/mail`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  catalog: () => req("/api/catalog"),
  catalogImport: (url: string) =>
    req("/api/catalog/import", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url }) }),
  catalogUpload: (file: File) => { const fd = new FormData(); fd.append("file", file); return req("/api/catalog/upload", { method: "POST", body: fd }); },
  setRule: (id: string, body: any) =>
    req(`/api/rules/${id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  fetchBlob: async (path: string) => {
    const res = await fetch(path, { headers: { Authorization: `Bearer ${getToken()}` } });
    if (res.status === 401) { setToken(null); window.location.href = "/login"; throw new Error(tr("Ej inloggad")); }
    if (!res.ok) throw await failure(res);
    return res.blob();
  },

  // ---- att driva tjänsten -------------------------------------------------------------------------------
  myRole: () => req("/api/me/role"),
  // credits: den gemensamma budgeten, med filter för period, person och del
  credits: (q: Record<string, string> = {}) => {
    const qs = new URLSearchParams(Object.entries(q).filter(([, v]) => v)).toString();
    return req(`/api/credits${qs ? `?${qs}` : ""}`);
  },
  creditsCsvPath: (q: Record<string, string> = {}) => {
    const qs = new URLSearchParams(Object.entries(q).filter(([, v]) => v)).toString();
    return `/api/credits.csv${qs ? `?${qs}` : ""}`;
  },
  price: (drawingId: string) => req(`/api/drawings/${drawingId}/price`),
  // röstsamtalets förbrukning, som OpenAI rapporterar den i samtalet: bokförs på den gemensamma budgeten
  liveUsage: (jobId: string, kind: "response" | "transcription", usage: any) =>
    req(`/api/jobs/${jobId}/live/usage`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ kind, usage }) }),
  contact: (body: { name: string; email: string; company?: string; subject?: string; message: string }) =>
    req("/api/public/contact", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  version: () => req("/api/version"),
  adm: (path: string) => req(`/api/admin/${path}`),
  admPut: (path: string, body?: any) =>
    req(`/api/admin/${path}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) }),
  admPost: (path: string, body: any) =>
    req(`/api/admin/${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),

  // ---- projektanalys ------------------------------------------------------------------------------------
  // Ett projekt utan valt läge svarar "simple" utan att skriva något: de gamla projekten fortsätter fungera
  // precis som förut tills någon väljer.
  mode: (projectId: string) => req(`/api/projects/${projectId}/mode`),
  setMode: (projectId: string, mode: string) =>
    req(`/api/projects/${projectId}/mode`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode }) }),
  projectAnalysis: (projectId: string) => req(`/api/projects/${projectId}/analysis`),
  startProjectAnalysis: (projectId: string) => req(`/api/projects/${projectId}/analysis`, { method: "POST" }),
  // Ändringslistan för ett versionspar. Den finns bara när båda bladen är mängdade var för sig - en sida som
  // inte lästs fylls aldrig i med noll, för då blir hela den lästa sidan "tillkommen".
  changes: (projectId: string, key: string) =>
    req(`/api/projects/${projectId}/analysis/changes?key=${encodeURIComponent(key)}`),
  // Vad en människa rättat om ett blad går före vad läsningen kom fram till, och ligger kvar när den körs om.
  overrides: (projectId: string) => req(`/api/projects/${projectId}/overrides`),
  setOverride: (projectId: string, body: { drawing_id: string; field: string; value: string; note?: string }) =>
    req(`/api/projects/${projectId}/overrides`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),

  // ---- akademin -----------------------------------------------------------------------------------------
  progress: () => req("/api/academy/progress"),
  saveProgress: (course: string, body: any) =>
    req(`/api/academy/progress/${course}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),

  awards: () => req("/api/academy/awards"),

  // ---- kalkyl och anbud ---------------------------------------------------------------------------------
  calcUnderlag: (jobId: string) => req(`/api/jobs/${jobId}/calc/underlag`),
  calcPreview: (jobId: string, body: any) =>
    req(`/api/jobs/${jobId}/calc/preview`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  calcSave: (jobId: string, body: any) =>
    req(`/api/jobs/${jobId}/calc`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  calc: (jobId: string) => req(`/api/jobs/${jobId}/calc`),
  anbudPdfUrl: (jobId: string) => `/api/jobs/${jobId}/calc/anbud.pdf`,
  anbudHtmlUrl: (jobId: string) => `/api/jobs/${jobId}/calc/anbud.html`,
  anbudInfo: (jobId: string) => req(`/api/jobs/${jobId}/calc/anbud`),
  anbudPageUrl: (jobId: string, n: number) => `/api/jobs/${jobId}/calc/anbud/sida-${n}.png`,

  // ---- projektagenten -----------------------------------------------------------------------------------
  projectAgent: (projectId: string, body: any) =>
    req(`/api/projects/${projectId}/agent`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  projectAgentTool: (projectId: string, name: string, args: any = {}) =>
    req(`/api/projects/${projectId}/agent/tool`, { method: "POST", headers: { "Content-Type": "application/json" },
                                                    body: JSON.stringify({ name, arguments: args }) }),

  // ---- egna markeringar på ritningen --------------------------------------------------------------------
  calibration: (drawingId: string, page = 0) => req(`/api/drawings/${drawingId}/calibration?page=${page}`),
  setCalibration: (drawingId: string, body: any) =>
    req(`/api/drawings/${drawingId}/calibration`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  clearCalibration: (drawingId: string, page = 0) =>
    req(`/api/drawings/${drawingId}/calibration?page=${page}`, { method: "DELETE" }),
  markupsCsvUrl: (drawingId: string, page = 0, allPages = false) =>
    `/api/drawings/${drawingId}/markups.csv?page=${page}${allPages ? "&all_pages=true" : ""}`,
  toolPresets: () => req("/api/tools"),
  addToolPreset: (body: any) => req("/api/tools", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  deleteToolPreset: (id: string) => req(`/api/tools/${id}`, { method: "DELETE" }),
  markups: (drawingId: string, page: number) => req(`/api/drawings/${drawingId}/markups?page=${page}`),
  // granskningen läser hela handlingen: en fråga ställd på sidan fyra hör inte ihop med vilken sida som visas
  allMarkups: (drawingId: string) => req(`/api/drawings/${drawingId}/markups?all_pages=true`),
  patchMarkup: (drawingId: string, id: string, change: any) =>
    req(`/api/drawings/${drawingId}/markups/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(change) }),
  patchMarkups: (drawingId: string, ids: string[], change: any) =>
    req(`/api/drawings/${drawingId}/markups`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ids, change }) }),
  addMarkup: (drawingId: string, body: any) =>
    req(`/api/drawings/${drawingId}/markups`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  updateMarkup: (drawingId: string, id: string, body: any) =>
    req(`/api/drawings/${drawingId}/markups/${id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  deleteMarkup: (drawingId: string, id: string) =>
    req(`/api/drawings/${drawingId}/markups/${id}`, { method: "DELETE" }),

  // ---- ritbordet: blad man ritar själv -------------------------------------------------------------------
  cadSheets: (projectId?: string) => req(`/api/cad/sheets${projectId ? `?project_id=${projectId}` : ""}`),
  cadCreate: (body: any) =>
    req("/api/cad/sheets", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  cadSheet: (id: string) => req(`/api/cad/sheets/${id}`),
  cadSave: (id: string, body: any) =>
    req(`/api/cad/sheets/${id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  cadDelete: (id: string) => req(`/api/cad/sheets/${id}`, { method: "DELETE" }),
  cadRevisions: (id: string) => req(`/api/cad/sheets/${id}/revisions`),
  cadRestore: (id: string, rev: number) => req(`/api/cad/sheets/${id}/revisions/${rev}/restore`, { method: "POST" }),
  cadQuantities: (id: string) => req(`/api/cad/sheets/${id}/quantities`),
  cadExportUrl: (id: string, fmt: "ifc" | "glb" | "svg" | "dxf" | "pdf", q: Record<string, string | number | undefined> = {}) =>
    `/api/cad/sheets/${id}/export.${fmt}${Object.keys(q).some((k) => q[k] != null) ? "?" + new URLSearchParams(Object.fromEntries(Object.entries(q).filter(([, v]) => v != null).map(([k, v]) => [k, String(v)]))).toString() : ""}`,
  cadSheetPdfUrl: (id: string, sheet: string) => `/api/cad/sheets/${id}/sheets/${sheet}.pdf`,
  cadImport: (id: string, file: File, level?: string, scaleRatio?: number) => { const fd = new FormData(); fd.append("file", file); if (level) fd.append("level", level); if (scaleRatio) fd.append("scale_ratio", String(scaleRatio)); return req(`/api/cad/sheets/${id}/import`, { method: "POST", body: fd }); },
  cadUnderlay: (id: string, src: { file?: File; drawing_id?: string; page?: number }) => {
    const fd = new FormData();
    if (src.file) fd.append("file", src.file);
    if (src.drawing_id) fd.append("drawing_id", src.drawing_id);
    fd.append("page", String(src.page ?? 0));
    return req(`/api/cad/sheets/${id}/underlay`, { method: "POST", body: fd });
  },
  cadAgent: (id: string, body: any) => req(`/api/cad/sheets/${id}/agent`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  cadAgentTool: (id: string, name: string, args: any = {}) =>
    req(`/api/cad/sheets/${id}/agent/tool`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, arguments: args }) }),
  /** En tillgång (underlag, nät) som en blob-URL med inloggningen gjord: bilder och laddare kan inte skicka en token själva. */
  cadAssetUrl: async (key: string): Promise<string> => {
    const cached = assetUrls.get(key); if (cached) return cached;
    const m = /^cad\/([^/]+)\/assets\/([^/]+)$/.exec(key); if (!m) throw new Error(tr("Okänd tillgång"));
    const b: Blob = await (api as any).fetchBlob(`/api/cad/assets/${m[1]}/${m[2]}`);
    const u = URL.createObjectURL(b); assetUrls.set(key, u); return u;
  },
  cadValidate: (content: any) =>
    req("/api/cad/validate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ content }) }),
  cadPrint: (id: string) => req(`/api/cad/sheets/${id}/tryck`, { method: "POST" }),
  cadPdfUrl: (id: string) => `/api/cad/sheets/${id}/pdf`,
  cadDxfUrl: (id: string) => `/api/cad/sheets/${id}/dxf`,
};

/* Vad besökaren gjorde, samlat ihop och skickat sällan.
 *
 * En händelse per anrop skulle betyda ett nätverksanrop per klick, och det är gränssnittets egen svarstid som
 * betalar för det. Så de samlas i en hink och töms med några sekunders mellanrum, och när fliken stängs.
 * Sessionsnyckeln byts när fliken stängs: den finns för att kunna räkna en besökare en gång i ett A/B-prov,
 * inte för att kunna följa någon.
 */
type Ev = { name: string; path?: string; x?: number; y?: number; target?: string; experiment?: string; variant?: string; meta?: any };
const bucket: Ev[] = [];
let flushing: any = null;

export function sessionKey(): string {
  try {
    let k = sessionStorage.getItem("vvs_session");
    if (!k) { k = Math.random().toString(36).slice(2) + Date.now().toString(36); sessionStorage.setItem("vvs_session", k); }
    return k;
  } catch { return "anon"; }
}

export function flushEvents(useBeacon = false) {
  if (!bucket.length) return;
  const body = JSON.stringify({ session: sessionKey(), events: bucket.splice(0, 60) });
  if (useBeacon && navigator.sendBeacon) {
    navigator.sendBeacon("/api/events", new Blob([body], { type: "application/json" }));
    return;
  }
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const tok = getToken();
  if (tok) headers["Authorization"] = `Bearer ${tok}`;
  fetch("/api/events", { method: "POST", headers, body, keepalive: true }).catch(() => { /* en förlorad händelse är ingen händelse */ });
}

export function track(e: Ev) {
  bucket.push({ ...e, path: e.path ?? window.location.pathname });
  if (bucket.length >= 40) { flushEvents(); return; }
  if (!flushing) flushing = setTimeout(() => { flushing = null; flushEvents(); }, 4000);
}

/** File size the way a person reads it, not in raw kilobytes. */
export function fileSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${num(bytes / 1024 / 1024, 1)} MB`;
  return `${Math.round(bytes / 1024)} kB`;
}
