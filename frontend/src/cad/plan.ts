/* Planen: hur byggmodellen ritas i 2D, träffas av pekaren och fångas mot.
 *
 * Allt ritas ur objekten själva - en vägg som sitt fotavtryck, en dörr som sitt slag, ett rör som sin bredd i
 * millimeter - och ingenting av det sparas. Samma segment som ritas används för fångst och träff, så det man
 * fångar är det man ser. */

import {
  type CadDocument, type Entity, type Pt, type View, type Wall, type Door, type Window, type Opening, type GridLine, type Underlay, type MeshRef,
  alongWall, dist, entity, visibleIn, wallLength,
} from "./building";
import { wallFootprint, profilePolygon, joinedWall } from "./solids";

import { locale } from "../i18n";
export type Seg = [Pt, Pt];
export type Cam = { s: number; ox: number; oy: number };       // skärm = värld·s + o
export const toScreen = (c: Cam, p: Pt): [number, number] => [p[0] * c.s + c.ox, p[1] * c.s + c.oy];
export const toWorld = (c: Cam, x: number, y: number): Pt => [(x - c.ox) / c.s, (y - c.oy) / c.s];

// ---------------------------------------------------------------- geometrin som segment

function polySegs(p: Pt[], closed: boolean): Seg[] {
  const out: Seg[] = [];
  for (let i = 0; i + 1 < p.length; i++) out.push([p[i], p[i + 1]]);
  if (closed && p.length > 2) out.push([p[p.length - 1], p[0]]);
  return out;
}
function arcPts(c: Pt, r: number, a0: number, a1: number): Pt[] {
  const n = Math.max(12, Math.round(Math.abs(a1 - a0) / 6));
  const out: Pt[] = [];
  for (let i = 0; i <= n; i++) { const a = ((a0 + ((a1 - a0) * i) / n) * Math.PI) / 180; out.push([c[0] + r * Math.cos(a), c[1] + r * Math.sin(a)]); }
  return out;
}

/** Objektets segment i planen, i världens millimeter. */
export function segmentsOf(doc: CadDocument, e: Entity): Seg[] {
  switch (e.type) {
    case "wall": case "curtain_wall": return polySegs(wallFootprint(e), true);
    case "door": case "window": case "opening": {
      const w = entity<Wall>(doc, e.host);
      if (!w || (w.type !== "wall" && w.type !== "curtain_wall")) return [];
      const L = wallLength(w) || 1;
      const { p, dir, n } = alongWall(w, e.t);
      const h = e.width / 2, t = w.thickness / 2;
      const a: Pt = [p[0] - dir[0] * h, p[1] - dir[1] * h], b: Pt = [p[0] + dir[0] * h, p[1] + dir[1] * h];
      void L;
      return [[[a[0] + n[0] * t, a[1] + n[1] * t], [a[0] - n[0] * t, a[1] - n[1] * t]], [[b[0] + n[0] * t, b[1] + n[1] * t], [b[0] - n[0] * t, b[1] - n[1] * t]]];
    }
    case "floor": case "roof": case "ceiling": case "room": return polySegs(e.p, true);
    case "foundation": return e.kind === "isolated" ? polySegs(profilePolygon({ kind: "rect", w: e.w ?? 1000, d: e.d ?? e.w ?? 1000 }, e.p[0]), true) : polySegs(e.p, e.kind === "slab");
    case "column": return polySegs(profilePolygon(e.profile, e.p[0], e.rot ?? 0), true);
    case "beam": case "truss": return [[e.p[0], e.p[1]]];
    case "stair": return [[e.p[0], e.p[1]]];
    case "railing": return polySegs(e.p, false);
    case "pipe": case "duct": case "cable_tray": case "conduit": return polySegs(e.path.map((q) => [q[0], q[1]] as Pt), false);
    case "fitting": case "device": return [[[e.p[0][0] - 60, e.p[0][1]], [e.p[0][0] + 60, e.p[0][1]]], [[e.p[0][0], e.p[0][1] - 60], [e.p[0][0], e.p[0][1] + 60]]];
    case "equipment": { const [c] = e.p; const [w, d] = e.size; return polySegs([[c[0] - w / 2, c[1] - d / 2], [c[0] + w / 2, c[1] - d / 2], [c[0] + w / 2, c[1] + d / 2], [c[0] - w / 2, c[1] + d / 2]], true); }
    case "site": return polySegs(e.p, !!e.closed);
    case "terrain": return [];
    case "line": return [[e.p[0], e.p[1]]];
    case "polyline": case "spline": return polySegs(e.p, !!e.closed);
    case "rect": { const [[x0, y0], [x1, y1]] = e.p; return polySegs([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], true); }
    case "circle": return polySegs(arcPts(e.p[0], e.r, 0, 360), false);
    case "arc": return polySegs(arcPts(e.p[0], e.r, e.a0, e.a1), false);
    case "ellipse": { const n = 36, pts: Pt[] = []; for (let i = 0; i <= n; i++) { const a = (2 * Math.PI * i) / n; pts.push([e.p[0][0] + e.rx * Math.cos(a), e.p[0][1] + e.ry * Math.sin(a)]); } return polySegs(pts, false); }
    case "dim": case "leader": return polySegs(e.p, false);
    case "hatch": return polySegs(e.p, true);
    case "text": case "mtext": return [];
    case "underlay": return polySegs(underlayCorners(e), true);
    case "mesh": return polySegs(meshFootprint(e), true);
    case "block": { const def = doc.blocks.find((b) => b.id === e.def); if (!def) return []; return def.entities.flatMap((x) => segmentsOf(doc, x as Entity).map(([a, b]) => [[a[0] + e.p[0][0] - def.origin[0], a[1] + e.p[0][1] - def.origin[1]], [b[0] + e.p[0][0] - def.origin[0], b[1] + e.p[0][1] - def.origin[1]]] as Seg)); }
    default: return [];
  }
}

/** Underlagets fyra hörn i planen: bildens pixlar gånger dess skala (1 mm/px tills den är uppmätt), vridet kring övre vänstra hörnet. */
export function underlayCorners(e: Underlay): Pt[] {
  const k = e.mm_per_px ?? 1;
  const w = e.px[0] * k, h = e.px[1] * k;
  const R = ((e.rot ?? 0) * Math.PI) / 180, c = Math.cos(R), s = Math.sin(R);
  const [x, y] = e.p[0];
  const P = (u: number, v: number): Pt => [x + u * c - v * s, y + u * s + v * c];
  return [P(0, 0), P(w, 0), P(w, h), P(0, h)];
}
/** Referensnätets låda i planen, ur filens egna mått gånger skalan; utan låda en halvmeters ruta så att det går att välja. */
export function meshFootprint(e: MeshRef): Pt[] {
  const [x, y] = e.p[0];
  const b = e.bounds;
  const w = b ? (b.max[0] - b.min[0]) * e.scale : 500, d = b ? (b.max[2] - b.min[2]) * e.scale : 500;   // glTF: y upp, z mot betraktaren ⇒ planens y är −z
  const x0 = b ? x + b.min[0] * e.scale : x - w / 2, y0 = b ? y - b.max[2] * e.scale : y - d / 2;
  return [[x0, y0], [x0 + w, y0], [x0 + w, y0 + d], [x0, y0 + d]];
}

export function bboxOf(doc: CadDocument, e: Entity): [number, number, number, number] {
  const pts: Pt[] = segmentsOf(doc, e).flat();
  if (e.type === "text" || e.type === "mtext") pts.push(e.p[0], [e.p[0][0] + (e.text.length * e.h * 0.6), e.p[0][1] - e.h]);
  if (!pts.length) return [0, 0, 0, 0];
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const [x, y] of pts) { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); }
  return [x0, y0, x1, y1];
}

function foot(p: Pt, a: Pt, b: Pt): { q: Pt; t: number } {
  const vx = b[0] - a[0], vy = b[1] - a[1];
  const L2 = vx * vx + vy * vy;
  if (!L2) return { q: a, t: 0 };
  const t = ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / L2;
  return { q: [a[0] + vx * t, a[1] + vy * t], t };
}
export function segDist(p: Pt, a: Pt, b: Pt): number {
  const { q, t } = foot(p, a, b);
  return t < 0 ? dist(p, a) : t > 1 ? dist(p, b) : dist(p, q);
}

/** Ligger punkten på objektet, inom tol millimeter? Ytor träffas även inuti (rum, bjälklag). */
export function hits(doc: CadDocument, e: Entity, p: Pt, tol: number): boolean {
  if (e.type === "text" || e.type === "mtext") { const [x0, y0, x1, y1] = bboxOf(doc, e); return p[0] >= x0 - tol && p[0] <= x1 + tol && p[1] >= Math.min(y0, y1) - tol && p[1] <= Math.max(y0, y1) + tol; }
  for (const [a, b] of segmentsOf(doc, e)) if (segDist(p, a, b) <= tol) return true;
  if (e.type === "room" || e.type === "floor" || e.type === "ceiling") {
    // inuti ytan, men inte om ett annat objekt ligger närmare: den som klickar mitt i rummet menar rummet
    let inside = false; const q = e.p;
    for (let i = 0, j = q.length - 1; i < q.length; j = i++) { const [xi, yi] = q[i], [xj, yj] = q[j]; if ((yi > p[1]) !== (yj > p[1]) && p[0] < ((xj - xi) * (p[1] - yi)) / (yj - yi) + xi) inside = !inside; }
    return inside;
  }
  return false;
}

/** Greppunkterna: det man drar i. Väggens ändar, konturens hörn, rörets punkter, pelarens centrum. */
export function gripsOf(e: Entity): Pt[] {
  switch (e.type) {
    case "wall": case "curtain_wall": case "beam": case "truss": case "stair": case "line": return [e.p[0], e.p[1]];
    case "floor": case "roof": case "ceiling": case "room": case "polyline": case "spline": case "railing": case "hatch": case "site": case "dim": case "leader": return e.p;
    case "foundation": return e.p;
    case "column": case "text": case "mtext": case "block": case "circle": case "arc": case "ellipse": case "underlay": return [e.p[0]];
    case "mesh": return [[e.p[0][0], e.p[0][1]]];
    case "rect": { const [[x0, y0], [x1, y1]] = e.p; return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]; }
    case "pipe": case "duct": case "cable_tray": case "conduit": return e.path.map((q) => [q[0], q[1]] as Pt);
    case "fitting": case "equipment": case "device": return [[e.p[0][0], e.p[0][1]]];
    default: return [];
  }
}

/** Flytta ett objekt. Det som sitter i en vägg flyttas inte självt: det följer väggen. */
export function moved(e: Entity, dx: number, dy: number): Entity {
  const mv = (p: Pt): Pt => [p[0] + dx, p[1] + dy];
  switch (e.type) {
    case "door": case "window": case "opening": return e;
    case "pipe": case "duct": case "cable_tray": case "conduit": return { ...e, path: e.path.map((q) => [q[0] + dx, q[1] + dy, q[2]]) } as Entity;
    case "fitting": case "equipment": case "device": case "mesh": return { ...e, p: [[e.p[0][0] + dx, e.p[0][1] + dy, e.p[0][2]]] } as Entity;
    case "terrain": return { ...e, points: e.points.map((q) => [q[0] + dx, q[1] + dy, q[2]]) } as Entity;
    case "roof": return { ...e, p: e.p.map(mv), ridge: e.ridge ? [mv(e.ridge[0]), mv(e.ridge[1])] : e.ridge } as Entity;
    default: return { ...(e as any), p: (e as any).p.map(mv) } as Entity;
  }
}

/** Ändra en greppunkt. */
export function gripped(e: Entity, i: number, p: Pt): Entity {
  switch (e.type) {
    case "pipe": case "duct": case "cable_tray": case "conduit": { const path = e.path.slice(); path[i] = [p[0], p[1], path[i]?.[2] ?? 0]; return { ...e, path } as Entity; }
    case "column": case "text": case "mtext": case "block": case "circle": case "arc": case "ellipse": return { ...(e as any), p: [p] } as Entity;
    case "fitting": case "equipment": case "device": return { ...e, p: [[p[0], p[1], e.p[0][2]]] } as Entity;
    case "rect": { const [[x0, y0], [x1, y1]] = e.p; const c = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]; c[i] = p; const xs = c.map((q) => q[0]), ys = c.map((q) => q[1]); return i === 0 ? { ...e, p: [p, [x1, y1]] } : i === 2 ? { ...e, p: [[x0, y0], p] } : { ...e, p: [[Math.min(...xs), Math.min(...ys)], [Math.max(...xs), Math.max(...ys)]] }; }
    case "door": case "window": case "opening": return e;
    default: { const q = ((e as any).p as Pt[]).slice(); q[i] = p; return { ...(e as any), p: q } as Entity; }
  }
}

// ---------------------------------------------------------------- fångst

export type SnapKind = "ändpunkt" | "mittpunkt" | "centrum" | "skärning" | "vinkelrät" | "närmast" | "rutnät" | "nät" | "fri";
export type Snap = { p: Pt; kind: SnapKind; from?: string };
export type SnapSettings = { on: boolean; grid: number; kinds: Record<Exclude<SnapKind, "fri">, boolean> };
export const defaultSnaps: SnapSettings = { on: true, grid: 100, kinds: { "ändpunkt": true, "mittpunkt": true, "centrum": true, "skärning": true, "vinkelrät": true, "närmast": true, "rutnät": true, "nät": true } };

function crossing(a: Pt, b: Pt, c: Pt, d: Pt): Pt | null {
  const r = [b[0] - a[0], b[1] - a[1]], s = [d[0] - c[0], d[1] - c[1]];
  const den = r[0] * s[1] - r[1] * s[0];
  if (Math.abs(den) < 1e-9) return null;
  const t = ((c[0] - a[0]) * s[1] - (c[1] - a[1]) * s[0]) / den;
  const u = ((c[0] - a[0]) * r[1] - (c[1] - a[1]) * r[0]) / den;
  if (t < 0 || t > 1 || u < 0 || u > 1) return null;
  return [a[0] + r[0] * t, a[1] + r[1] * t];
}

export function snapPoint(doc: CadDocument, view: View, raw: Pt, set: SnapSettings, tol: number, ref?: Pt | null): Snap {
  if (!set.on) return { p: raw, kind: "fri" };
  const cands: Snap[] = [];
  const near: Seg[] = [];
  const consider = (segs: Seg[], id: string, centre?: Pt) => {
    if (centre && set.kinds.centrum) cands.push({ p: centre, kind: "centrum", from: id });
    for (const [a, b] of segs) {
      if (Math.min(a[0], b[0]) > raw[0] + tol || Math.max(a[0], b[0]) < raw[0] - tol || Math.min(a[1], b[1]) > raw[1] + tol || Math.max(a[1], b[1]) < raw[1] - tol) continue;
      near.push([a, b]);
      if (set.kinds["ändpunkt"]) { cands.push({ p: a, kind: "ändpunkt", from: id }); cands.push({ p: b, kind: "ändpunkt", from: id }); }
      if (set.kinds.mittpunkt) cands.push({ p: [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2], kind: "mittpunkt", from: id });
      if (set.kinds["närmast"]) { const { q, t } = foot(raw, a, b); if (t >= 0 && t <= 1) cands.push({ p: q, kind: "närmast", from: id }); }
      if (set.kinds["vinkelrät"] && ref) { const { q, t } = foot(ref, a, b); if (t >= 0 && t <= 1) cands.push({ p: q, kind: "vinkelrät", from: id }); }
    }
  };
  for (const e of doc.entities) {
    if (!visibleIn(doc, view, e)) continue;
    const [x0, y0, x1, y1] = bboxOf(doc, e);
    if (raw[0] < x0 - tol || raw[0] > x1 + tol || raw[1] < y0 - tol || raw[1] > y1 + tol) continue;
    const centre = e.type === "column" || e.type === "circle" || e.type === "arc" ? e.p[0] : e.type === "wall" || e.type === "curtain_wall" ? undefined : undefined;
    consider(segmentsOf(doc, e), e.id, centre);
    if (e.type === "wall" || e.type === "curtain_wall") consider([[e.p[0], e.p[1]]], e.id);   // centrumlinjen också
  }
  if (set.kinds["nät"]) for (const g of doc.grids) consider([g.p], `grid:${g.id}`);
  if (set.kinds["skärning"]) {
    for (let i = 0; i < near.length; i++) for (let j = i + 1; j < near.length; j++) {
      const q = crossing(near[i][0], near[i][1], near[j][0], near[j][1]);
      if (q && dist(q, raw) <= tol) cands.push({ p: q, kind: "skärning" });
    }
  }
  const rank: Record<SnapKind, number> = { "ändpunkt": 0, "skärning": 1, "mittpunkt": 2, "centrum": 3, "vinkelrät": 4, "nät": 5, "närmast": 6, "rutnät": 7, "fri": 8 };
  let best: Snap | null = null, bestScore = Infinity;
  for (const c of cands) {
    const d = dist(c.p, raw);
    if (d > tol) continue;
    const score = rank[c.kind] * tol + d;
    if (score < bestScore) { best = c; bestScore = score; }
  }
  if (best) return best;
  if (set.kinds["rutnät"] && set.grid > 0) {
    const g: Pt = [Math.round(raw[0] / set.grid) * set.grid, Math.round(raw[1] / set.grid) * set.grid];
    if (dist(g, raw) <= tol) return { p: g, kind: "rutnät" };
  }
  return { p: raw, kind: "fri" };
}

/** Punkten låst mot ortho (90) eller polär (45) vinkel från `from`. */
export function constrain(from: Pt | null | undefined, to: Pt, step: number): Pt {
  if (!from || !step) return to;
  const d = dist(from, to);
  if (!d) return to;
  const a = Math.atan2(to[1] - from[1], to[0] - from[0]);
  const q = Math.round(a / ((step * Math.PI) / 180)) * ((step * Math.PI) / 180);
  return [from[0] + d * Math.cos(q), from[1] + d * Math.sin(q)];
}

/** Var på en vägg en punkt ligger: andelen längs centrumlinjen, och avståndet från den. */
export function onWall(w: Wall, p: Pt): { t: number; d: number } {
  const { q, t } = foot(p, w.p[0], w.p[1]);
  return { t: Math.max(0, Math.min(1, t)), d: dist(p, q) };
}

/** Närmaste vägg till en punkt inom tol, för att placera dörrar och fönster. */
export function wallAt(doc: CadDocument, view: View, p: Pt, tol: number): { wall: Wall; t: number } | null {
  let best: { wall: Wall; t: number; d: number } | null = null;
  for (const e of doc.entities) {
    if ((e.type !== "wall" && e.type !== "curtain_wall") || !visibleIn(doc, view, e)) continue;
    const { t, d } = onWall(e as Wall, p);
    if (d <= Math.max(tol, e.thickness / 2 + tol) && (!best || d < best.d)) best = { wall: e as Wall, t, d };
  }
  return best ? { wall: best.wall, t: best.t } : null;
}

// ---------------------------------------------------------------- ritning

export type PlanStyle = {
  colour: (e: Entity) => string; selected: Set<string>; hover?: Snap | null; ghost?: Entity | null; cam: Cam; scale_ratio: number; showGrid: number;
  ghosts?: Entity[];                                       // förslag som inte är godkända än
  images?: Map<string, HTMLImageElement | null>;           // underlagens bilder, laddade av sidan
};

const DISC_COLOUR: Record<string, string> = { ARK: "#111111", KONSTR: "#7048e8", VVS: "#1f6feb", VENT: "#0b7285", EL: "#b58900", SPRINKLER: "#c0392b", BRAND: "#c0392b", MARK: "#2f9e44", UTRUSTNING: "#5c7080", ALLMAN: "#444444" };
export function colourOf(doc: CadDocument, e: Entity): string {
  const layer = doc.layers.find((l) => l.id === e.layer);
  if (e.type === "pipe" && e.system) { const s = e.system.toUpperCase(); if (s.startsWith("KV")) return "#1f6feb"; if (s.startsWith("VV")) return "#c0392b"; if (s.startsWith("S")) return "#2f9e44"; }
  return layer?.color || DISC_COLOUR[e.discipline] || "#111";
}

export function drawPlan(g: CanvasRenderingContext2D, doc: CadDocument, view: View, st: PlanStyle, size: [number, number]) {
  const { cam } = st;
  const S = (p: Pt) => toScreen(cam, p);
  g.clearRect(0, 0, size[0], size[1]);
  g.fillStyle = "#fbfbfa"; g.fillRect(0, 0, size[0], size[1]);
  // rutnätet
  if (st.showGrid > 0) {
    let step = st.showGrid; while (step * cam.s < 9) step *= 5;
    const w0 = toWorld(cam, 0, 0), w1 = toWorld(cam, size[0], size[1]);
    g.strokeStyle = "#ececea"; g.lineWidth = 1; g.beginPath();
    for (let x = Math.floor(w0[0] / step) * step; x <= w1[0]; x += step) { const sx = Math.round(S([x, 0])[0]) + 0.5; g.moveTo(sx, 0); g.lineTo(sx, size[1]); }
    for (let y = Math.floor(w0[1] / step) * step; y <= w1[1]; y += step) { const sy = Math.round(S([0, y])[1]) + 0.5; g.moveTo(0, sy); g.lineTo(size[0], sy); }
    g.stroke();
    // origo
    const o = S([0, 0]); g.strokeStyle = "#c9c9c4"; g.beginPath(); g.moveTo(o[0] - 8, o[1]); g.lineTo(o[0] + 8, o[1]); g.moveTo(o[0], o[1] - 8); g.lineTo(o[0], o[1] + 8); g.stroke();
  }
  // byggrutnätet: linjer med bubblor
  for (const gl of doc.grids) {
    const A = S(gl.p[0]), B = S(gl.p[1]);
    g.strokeStyle = "#8a8f98"; g.setLineDash([12, 4, 3, 4]); g.lineWidth = 1; g.beginPath(); g.moveTo(A[0], A[1]); g.lineTo(B[0], B[1]); g.stroke(); g.setLineDash([]);
    for (const P of [A, B]) { g.beginPath(); g.arc(P[0], P[1], 11, 0, Math.PI * 2); g.fillStyle = "#fff"; g.fill(); g.stroke(); g.fillStyle = "#333"; g.font = "11px ui-monospace, monospace"; g.textAlign = "center"; g.textBaseline = "middle"; g.fillText(gl.label, P[0], P[1]); }
    g.textAlign = "left"; g.textBaseline = "alphabetic";
  }
  const ents = doc.entities.filter((e) => visibleIn(doc, view, e));
  // underlagen längst ner: bilder att rita mot
  for (const e of ents) if (e.type === "underlay") drawUnderlay(g, e, st);
  // ytor först, sedan väggar, sedan MEP och text
  const order = (e: Entity) => (e.type === "floor" || e.type === "room" || e.type === "site" || e.type === "terrain" || e.type === "hatch" ? 0 : e.type === "roof" || e.type === "ceiling" ? 1 : e.type === "wall" || e.type === "curtain_wall" || e.type === "column" || e.type === "foundation" ? 2 : e.type === "door" || e.type === "window" || e.type === "opening" || e.type === "beam" || e.type === "stair" || e.type === "railing" ? 3 : e.type === "text" || e.type === "mtext" || e.type === "dim" || e.type === "leader" ? 5 : 4);
  for (const e of [...ents].sort((a, b) => order(a) - order(b))) drawEntity(g, doc, e, st, false);
  if (st.ghost) drawEntity(g, doc, st.ghost, st, true);
  for (const e of st.ghosts ?? []) drawEntity(g, doc, e, st, true);
  // markering och grepp
  for (const e of ents) if (st.selected.has(e.id)) {
    const [x0, y0, x1, y1] = bboxOf(doc, e); const A = S([x0, y0]), B = S([x1, y1]);
    g.strokeStyle = "#1f6feb"; g.lineWidth = 1; g.setLineDash([4, 3]); g.strokeRect(Math.min(A[0], B[0]) - 4, Math.min(A[1], B[1]) - 4, Math.abs(B[0] - A[0]) + 8, Math.abs(B[1] - A[1]) + 8); g.setLineDash([]);
    g.fillStyle = "#1f6feb"; for (const gp of gripsOf(e)) { const P = S(gp); g.fillRect(P[0] - 3.5, P[1] - 3.5, 7, 7); }
  }
  // fångstmarkören
  const h = st.hover;
  if (h && h.kind !== "fri") {
    const P = S(h.p); g.strokeStyle = "#e8590c"; g.lineWidth = 1.6; g.beginPath();
    if (h.kind === "ändpunkt") g.strokeRect(P[0] - 5, P[1] - 5, 10, 10);
    else if (h.kind === "mittpunkt") { g.moveTo(P[0] - 6, P[1] + 4); g.lineTo(P[0], P[1] - 6); g.lineTo(P[0] + 6, P[1] + 4); g.closePath(); g.stroke(); }
    else if (h.kind === "centrum" || h.kind === "nät") { g.arc(P[0], P[1], 5.5, 0, Math.PI * 2); g.stroke(); }
    else if (h.kind === "skärning") { g.moveTo(P[0] - 6, P[1] - 6); g.lineTo(P[0] + 6, P[1] + 6); g.moveTo(P[0] + 6, P[1] - 6); g.lineTo(P[0] - 6, P[1] + 6); g.stroke(); }
    else if (h.kind === "vinkelrät") { g.strokeRect(P[0] - 5, P[1] - 5, 10, 10); g.moveTo(P[0] - 5, P[1] + 5); g.lineTo(P[0] + 5, P[1] + 5); g.stroke(); }
    else { g.arc(P[0], P[1], 3.5, 0, Math.PI * 2); g.stroke(); }
  }
}

function drawUnderlay(g: CanvasRenderingContext2D, e: Underlay, st: PlanStyle) {
  const { cam } = st;
  const corners = underlayCorners(e);
  const img = st.images?.get(e.asset);
  const k = e.mm_per_px ?? 1;
  const A = toScreen(cam, e.p[0]);
  g.save();
  g.translate(A[0], A[1]); g.rotate(((e.rot ?? 0) * Math.PI) / 180);
  g.globalAlpha = e.opacity ?? 0.6;
  if (img) g.drawImage(img, 0, 0, e.px[0] * k * cam.s, e.px[1] * k * cam.s);
  else { g.fillStyle = "#e9e9e6"; g.fillRect(0, 0, e.px[0] * k * cam.s, e.px[1] * k * cam.s); }
  g.restore();
  g.globalAlpha = 1;
  if (e.scale_state === "UNCALIBRATED") {
    g.strokeStyle = "#e8590c"; g.setLineDash([6, 4]); g.lineWidth = 1; g.beginPath();
    corners.forEach((p, i) => { const P = toScreen(cam, p); if (i) g.lineTo(P[0], P[1]); else g.moveTo(P[0], P[1]); }); g.closePath(); g.stroke(); g.setLineDash([]);
    g.fillStyle = "#e8590c"; g.font = "11px ui-monospace, monospace"; g.fillText("underlag utan skala - kalibrera", A[0] + 6, A[1] + 14);
  }
}

/** Vad en text visar: sin egen text, eller det fält på objektet den hänger på. Ett brutet band visar det. */
export function tagText(doc: CadDocument, e: Extract<Entity, { type: "text" }>): string {
  if (!e.ref) return e.text;
  const t = entity(doc, e.ref.id);
  if (!t) return `[${e.ref.id} saknas]`;
  switch (e.ref.field) {
    case "name": return (t as any).name ?? "";
    case "number": return (t as any).number ?? "";
    case "id": return t.id;
    case "level": return doc.levels.find((l) => l.id === ((t as any).base_level ?? (t as any).level))?.name ?? "";
    case "system": return (t as any).system ?? "";
    case "dn": return (t as any).dn != null ? `DN${(t as any).dn}` : "";
    case "area": { const p: Pt[] = (t as any).p ?? []; if (p.length < 3) return ""; let a = 0; for (let i = 0; i < p.length; i++) { const q = p[(i + 1) % p.length]; a += p[i][0] * q[1] - q[0] * p[i][1]; } return `${(Math.abs(a) / 2 / 1e6).toFixed(1)} m²`; }
    case "length": { if ("path" in t) { const q = (t as any).path; let L = 0; for (let i = 0; i + 1 < q.length; i++) L += Math.hypot(q[i + 1][0] - q[i][0], q[i + 1][1] - q[i][1], (q[i + 1][2] ?? 0) - (q[i][2] ?? 0)); return `${(L / 1000).toFixed(2)} m`; } const p: Pt[] = (t as any).p ?? []; return p.length >= 2 ? `${Math.round(dist(p[0], p[1]))}` : ""; }
  }
}

function drawEntity(g: CanvasRenderingContext2D, doc: CadDocument, e: Entity, st: PlanStyle, ghost: boolean) {
  const { cam } = st; const S = (p: Pt) => toScreen(cam, p);
  const col = ghost ? "#1f6feb" : st.colour(e);
  const mm = (w: number) => Math.max(1, w * cam.s);
  g.strokeStyle = col; g.fillStyle = col; g.setLineDash(ghost ? [6, 4] : []); g.lineWidth = 1.2;
  const poly = (pts: Pt[], close: boolean) => { g.beginPath(); pts.forEach((p, i) => { const P = S(p); if (i) g.lineTo(P[0], P[1]); else g.moveTo(P[0], P[1]); }); if (close) g.closePath(); };
  switch (e.type) {
    case "wall": case "curtain_wall": {
      // hörnen sluts: väggen går vidare in i hörnet mot en vägg som slutar där (solids.wallJoins)
      const fp = wallFootprint(ghost ? e : joinedWall(doc, e).wall); poly(fp, true);
      // en ny vägg målas täckande, så att två väggar som möts i ett hörn inte blir mörkare där de ligger på varandra
      g.fillStyle = ghost ? "rgba(31,111,235,0.15)" : e.type === "curtain_wall" ? "rgba(159,211,232,0.5)" : e.phase === "DEMOLISH" ? "rgba(200,60,60,0.18)" : e.phase === "EXISTING" ? "rgba(120,120,120,0.25)" : "rgb(72,72,72)";
      g.fill(); g.lineWidth = 1; g.stroke();
      break;
    }
    case "door": {
      const w = entity<Wall>(doc, e.host); if (!w) break;
      const { p, dir, n } = alongWall(w, e.t); const h = e.width / 2, t = w.thickness / 2;
      const a: Pt = [p[0] - dir[0] * h, p[1] - dir[1] * h], b: Pt = [p[0] + dir[0] * h, p[1] + dir[1] * h];
      // öppningen: vit över väggen, sedan slaget
      poly([[a[0] + n[0] * t, a[1] + n[1] * t], [b[0] + n[0] * t, b[1] + n[1] * t], [b[0] - n[0] * t, b[1] - n[1] * t], [a[0] - n[0] * t, a[1] - n[1] * t]], true);
      g.fillStyle = "#fbfbfa"; g.fill(); g.strokeStyle = col; g.lineWidth = 1; g.stroke();
      const hinge = e.swing === "right" ? b : a, sign = e.swing === "right" ? -1 : 1;
      const leaf: Pt = [hinge[0] + n[0] * e.width * sign, hinge[1] + n[1] * e.width * sign];
      const H = S(hinge), L = S(leaf); g.beginPath(); g.moveTo(H[0], H[1]); g.lineTo(L[0], L[1]); g.lineWidth = Math.max(1, 40 * cam.s); g.stroke();
      const a0 = Math.atan2(L[1] - H[1], L[0] - H[0]), other = S(e.swing === "right" ? a : b), a1 = Math.atan2(other[1] - H[1], other[0] - H[0]);
      g.lineWidth = 1; g.beginPath(); g.arc(H[0], H[1], e.width * cam.s, Math.min(a0, a1), Math.max(a0, a1)); g.stroke();
      break;
    }
    case "window": case "opening": {
      const w = entity<Wall>(doc, e.host); if (!w) break;
      const { p, dir, n } = alongWall(w, e.t); const h = e.width / 2, t = w.thickness / 2;
      const a: Pt = [p[0] - dir[0] * h, p[1] - dir[1] * h], b: Pt = [p[0] + dir[0] * h, p[1] + dir[1] * h];
      poly([[a[0] + n[0] * t, a[1] + n[1] * t], [b[0] + n[0] * t, b[1] + n[1] * t], [b[0] - n[0] * t, b[1] - n[1] * t], [a[0] - n[0] * t, a[1] - n[1] * t]], true);
      g.fillStyle = "#fbfbfa"; g.fill(); g.strokeStyle = col; g.lineWidth = 1; g.stroke();
      if (e.type === "window") { const A = S(a), B = S(b); g.beginPath(); g.moveTo(A[0], A[1]); g.lineTo(B[0], B[1]); g.strokeStyle = "#1f6feb"; g.lineWidth = Math.max(1.5, 30 * cam.s); g.stroke(); }
      break;
    }
    case "floor": case "ceiling": { poly(e.p, true); g.fillStyle = ghost ? "rgba(31,111,235,0.08)" : e.type === "floor" ? "rgba(120,130,140,0.08)" : "rgba(180,160,90,0.10)"; g.fill(); g.setLineDash(e.type === "ceiling" ? [8, 4] : []); g.stroke(); g.setLineDash([]); break; }
    case "roof": { poly(e.p, true); g.setLineDash([10, 5]); g.strokeStyle = "#8a6d3b"; g.stroke(); g.setLineDash([]); if (e.ridge) { const A = S(e.ridge[0]), B = S(e.ridge[1]); g.beginPath(); g.moveTo(A[0], A[1]); g.lineTo(B[0], B[1]); g.lineWidth = 2; g.stroke(); } break; }
    case "room": {
      poly(e.p, true); g.fillStyle = ghost ? "rgba(31,111,235,0.08)" : "rgba(0, 181, 226,0.10)"; g.fill();
      let cx = 0, cy = 0; for (const p of e.p) { cx += p[0]; cy += p[1]; } const C = S([cx / e.p.length, cy / e.p.length]);
      const area = Math.abs(e.p.reduce((s, p, i) => { const q = e.p[(i + 1) % e.p.length]; return s + p[0] * q[1] - q[0] * p[1]; }, 0)) / 2 / 1e6;
      g.fillStyle = "#1b4d33"; g.font = "12px system-ui, sans-serif"; g.textAlign = "center"; g.fillText(`${e.number ? e.number + " " : ""}${e.name || "Rum"}`, C[0], C[1] - 2); g.font = "11px ui-monospace, monospace"; g.fillText(`${area.toLocaleString(locale(), { maximumFractionDigits: 1 })} m²`, C[0], C[1] + 12); g.textAlign = "left";
      break;
    }
    case "column": { poly(profilePolygon(e.profile, e.p[0], e.rot ?? 0), true); g.fillStyle = ghost ? "rgba(31,111,235,0.3)" : "rgba(112,72,232,0.85)"; g.fill(); g.stroke(); break; }
    case "beam": case "truss": { const A = S(e.p[0]), B = S(e.p[1]); g.beginPath(); g.moveTo(A[0], A[1]); g.lineTo(B[0], B[1]); g.lineWidth = mm(e.profile.kind === "circle" ? e.profile.d : e.profile.w); g.strokeStyle = ghost ? col : "rgba(112,72,232,0.45)"; g.stroke(); g.lineWidth = 1; g.setLineDash([6, 3]); g.strokeStyle = "#7048e8"; g.stroke(); g.setLineDash([]); break; }
    case "foundation": { for (const [a, b] of segmentsOf(doc, e)) { const A = S(a), B = S(b); g.beginPath(); g.moveTo(A[0], A[1]); g.lineTo(B[0], B[1]); g.setLineDash([3, 3]); g.stroke(); } g.setLineDash([]); break; }
    case "stair": {
      const [a, b] = e.p; const L = dist(a, b) || 1; const dir: Pt = [(b[0] - a[0]) / L, (b[1] - a[1]) / L], n: Pt = [-dir[1] * e.width / 2, dir[0] * e.width / 2];
      for (let i = 0; i <= e.risers; i++) { const t = Math.min(L, i * e.tread_d); const p: Pt = [a[0] + dir[0] * t, a[1] + dir[1] * t]; const A = S([p[0] + n[0], p[1] + n[1]]), B = S([p[0] - n[0], p[1] - n[1]]); g.beginPath(); g.moveTo(A[0], A[1]); g.lineTo(B[0], B[1]); g.stroke(); }
      const A = S([a[0] + n[0], a[1] + n[1]]), B = S([b[0] + n[0], b[1] + n[1]]), C = S([b[0] - n[0], b[1] - n[1]]), D = S([a[0] - n[0], a[1] - n[1]]); g.beginPath(); g.moveTo(A[0], A[1]); g.lineTo(B[0], B[1]); g.moveTo(C[0], C[1]); g.lineTo(D[0], D[1]); g.stroke();
      const M = S([(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]); g.font = "10px ui-monospace, monospace"; g.fillText("UPP", M[0] + 4, M[1] - 4);
      break;
    }
    case "pipe": case "duct": case "cable_tray": case "conduit": {
      const pts = e.path.map((q) => [q[0], q[1]] as Pt); poly(pts, false);
      const w = e.type === "pipe" ? e.dn : e.type === "duct" ? (e.shape === "round" ? e.d ?? 200 : e.w ?? 400) : e.type === "cable_tray" ? e.w : e.d;
      g.lineWidth = Math.max(1.5, w * cam.s); g.lineCap = "round"; g.lineJoin = "round"; g.globalAlpha = e.type === "pipe" ? 1 : 0.8; g.stroke(); g.globalAlpha = 1;
      if (e.type === "duct") { g.lineWidth = 1; g.strokeStyle = "#fff"; g.setLineDash([4, 4]); g.stroke(); g.setLineDash([]); }
      if (e.type === "pipe" && (e.designation || e.system) && cam.s > 0.02) { const P = S(pts[0]); g.font = "11px ui-monospace, monospace"; g.fillStyle = col; g.fillText(`${e.designation || e.system} DN${e.dn}`, P[0] + 6, P[1] - 6); }
      break;
    }
    case "fitting": case "device": { const P = S([e.p[0][0], e.p[0][1]]); g.beginPath(); g.arc(P[0], P[1], 5, 0, Math.PI * 2); g.stroke(); break; }
    case "equipment": { for (const [a, b] of segmentsOf(doc, e)) { const A = S(a), B = S(b); g.beginPath(); g.moveTo(A[0], A[1]); g.lineTo(B[0], B[1]); g.stroke(); } const [c] = e.p; const P = S([c[0], c[1]]); g.font = "10px system-ui"; g.fillText(e.name || e.kind, P[0] + 4, P[1] + 4); break; }
    case "text": case "mtext": { const P = S(e.p[0]); const px = Math.max(8, e.h * st.scale_ratio * cam.s); g.save(); g.translate(P[0], P[1]); g.rotate(-((e.rot ?? 0) * Math.PI) / 180); g.font = `${px}px ui-monospace, monospace`; g.fillText(e.type === "text" ? tagText(doc, e) : e.text, 0, 0); g.restore(); break; }
    case "dim": {
      if (e.p.length < 2) break;
      const [a, b] = e.p; const L = dist(a, b) || 1; const n: Pt = [-(b[1] - a[1]) / L * e.off, (b[0] - a[0]) / L * e.off];
      const A = S([a[0] + n[0], a[1] + n[1]]), B = S([b[0] + n[0], b[1] + n[1]]), A0 = S(a), B0 = S(b);
      g.lineWidth = 1; g.beginPath(); g.moveTo(A0[0], A0[1]); g.lineTo(A[0], A[1]); g.moveTo(B0[0], B0[1]); g.lineTo(B[0], B[1]); g.moveTo(A[0], A[1]); g.lineTo(B[0], B[1]); g.stroke();
      for (const P of [A, B]) { g.beginPath(); g.moveTo(P[0] - 4, P[1] + 4); g.lineTo(P[0] + 4, P[1] - 4); g.stroke(); }
      const M: [number, number] = [(A[0] + B[0]) / 2, (A[1] + B[1]) / 2]; g.font = "11px ui-monospace, monospace"; g.textAlign = "center"; g.fillText(`${Math.round(L)}`, M[0], M[1] - 4); g.textAlign = "left";
      break;
    }
    case "leader": { poly(e.p, false); g.stroke(); const P = S(e.p[e.p.length - 1]); g.font = "11px ui-monospace, monospace"; g.fillText(e.text, P[0] + 4, P[1] - 4); break; }
    case "hatch": { poly(e.p, true); g.fillStyle = "rgba(0,0,0,0.06)"; g.fill(); g.stroke(); break; }
    case "underlay": { if (ghost || st.selected.has(e.id)) { poly(underlayCorners(e), true); g.stroke(); } break; }
    case "mesh": { poly(meshFootprint(e), true); g.setLineDash([2, 3]); g.stroke(); g.setLineDash([]); const P = S([e.p[0][0], e.p[0][1]]); g.font = "10px ui-monospace, monospace"; g.fillText(e.filename ?? e.format, P[0] + 4, P[1] - 4); break; }
    default: { for (const [a, b] of segmentsOf(doc, e)) { const A = S(a), B = S(b); g.beginPath(); g.moveTo(A[0], A[1]); g.lineTo(B[0], B[1]); g.stroke(); } }
  }
  g.setLineDash([]); g.lineWidth = 1; g.globalAlpha = 1;
}

export type PlanTag = { id: string; label: string };
export function gridLabels(doc: CadDocument): PlanTag[] { return doc.grids.map((g: GridLine) => ({ id: g.id, label: g.label })); }
export function hostedOf(doc: CadDocument, id: string): (Door | Window | Opening)[] { return doc.entities.filter((e) => (e.type === "door" || e.type === "window" || e.type === "opening") && e.host === id) as any; }
