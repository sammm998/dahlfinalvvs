"""Artifact writers: all per-drawing JSON / markdown outputs and the evidence graph."""
from __future__ import annotations

import hashlib
import json
import os
import re
import platform
import subprocess
import time
from collections import Counter
from typing import Any

from .. import __version__
from .schema import ARTIFACT_SCHEMA, stamp
from ..profile.layers import layer_tokens
from ..pipeline import reading_coverage
from ..measure.measure import SETTLED_SCALE
from ..semantics.leaders import leader_family_report
from ..pipes.confidence import tier


def _from_image(pa) -> bool:
    """Whether the sheet was read from pixels (raster/) rather than from its own vectors."""
    return ((getattr(pa.page, "input_class", None) or {}).get("read_as")) == "raster"


def _dump(path: str, obj: Any) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(stamp(obj), fh, indent=1, ensure_ascii=False, sort_keys=False, default=str)


def _sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def drawing_profile(pa, doc) -> dict[str, Any]:
    page = pa.page
    des_fams = Counter(d.family for d in pa.designations)
    anchors_by_des = {}
    for a in pa.anchors:
        anchors_by_des.setdefault(a.designation_id, []).append(a.state)
    def fam_stats(fam):
        ds = [d for d in pa.designations if d.family == fam]
        conf = sum(1 for d in ds if any(s == "VERIFIED_PIPE_ATTACHMENT" for s in anchors_by_des.get(d.did, [])))
        amb = sum(1 for d in ds if any(s == "AMBIGUOUS_PIPE_ATTACHMENT" for s in anchors_by_des.get(d.did, [])) and not any(s == "VERIFIED_PIPE_ATTACHMENT" for s in anchors_by_des.get(d.did, [])))
        return {"family": fam, "occurrences": len(ds), "processed": len(ds), "confirmed": conf, "ambiguous": amb, "unsupported": len(ds) - conf - amb,
                "examples": sorted({d.text for d in ds})[:6]}
    text_fams = Counter(r.family for r in pa.lines)
    leader_rep = leader_family_report(pa.leaders)
    ld_state = {}
    for a in pa.anchors:
        ld_state.setdefault(a.leader_id, set()).add(a.state)
    lfam_rows = []
    for f in leader_rep["families"]:
        fam = f["family"]
        lids = [l.lid for l in pa.leaders if l.family == fam]
        conf = sum(1 for l in lids if "VERIFIED_PIPE_ATTACHMENT" in ld_state.get(l, set()))
        amb = sum(1 for l in lids if "AMBIGUOUS_PIPE_ATTACHMENT" in ld_state.get(l, set()) and "VERIFIED_PIPE_ATTACHMENT" not in ld_state.get(l, set()))
        lfam_rows.append({"family": fam, "occurrences": len(lids), "processed": len(lids), "confirmed": conf, "ambiguous": amb, "unsupported": len(lids) - conf - amb})
    marker_fams = Counter()
    for l in pa.leaders:
        for m in l.end_marks:
            marker_fams[f"end-tick|{m.layer}|{m.style}"] += 1
        for m in l.crossing_marks:
            marker_fams[f"crossing-tick|{m.layer}|{m.style}"] += 1
    pipe_fams = []
    for fk, rf in pa.pipe_families.items():
        sts = pa.ownership.prim_states[fk]
        pipe_fams.append({**rf.as_dict(), "occurrences": rf.n_prims, "processed": rf.n_prims,
                          "confirmed": sum(1 for s in sts.values() if s.state == "CONFIRMED"),
                          "ambiguous": sum(1 for s in sts.values() if s.state == "AMBIGUOUS"),
                          "unsupported": 0, "unowned": sum(1 for s in sts.values() if s.state == "UNOWNED"),
                          "system_tokens": [t for t in layer_tokens(rf.layer) if len(t) >= 2]})
    unsupported = []
    for fam, n in des_fams.items():
        st = fam_stats(fam)
        if st["confirmed"] == 0 and st["ambiguous"] == 0 and n >= 3:
            unsupported.append({"family": fam, "kind": "code family without any verified pipe attachment (component tags / non-pipe codes)", "occurrences": n, "examples": st["examples"]})
    layers = []
    for name, st in sorted(pa.layer_stats.items()):
        role = "UNKNOWN"
        fams_here = [fk for fk in pa.pipe_families if fk.startswith(name + "|")]
        if fams_here:
            role = "PIPE_GEOMETRY"
        elif any(k.startswith(name + "|") for k in pa.ann_layers):
            role = "VVS_ANNOTATION"
        elif any(m.layer == name for l in pa.leaders for m in l.end_marks + l.crossing_marks):
            role = "CONNECTOR"
        layers.append({**st.as_dict(), "role": role})
    return {
        "engine_version": __version__,
        "page_structure": {"page": page.info.index, "width_pt": page.info.width, "height_pt": page.info.height, "rotation": page.info.rotation,
                           "mediabox": page.info.mediabox, "cropbox": page.info.cropbox, "n_pages": doc.n_pages, "format": _fmt(page)},
        "input": {"mode": "vector", "classification": getattr(page, "input_class", None)},
        "cad_structure": {"n_ocgs": len(doc.ocgs), "n_layers_with_geometry": len(pa.layer_stats), "n_xobjects": page.info.n_xobjects,
                          "layers": layers, "annotation_layers": pa.ann_layers},
        "text_structure": {"searchable_spans": len(page.spans), "searchable_rows": len(pa.srows), "vector_glyph_rows": len(pa.vtext.rows),
                           "glyph_components": pa.vtext.n_components, "glyphs": pa.vtext.n_glyphs, "glyph_families": len(pa.vtext.families),
                           "unknown_glyph_families": pa.vtext.stats.get("unknown_families"), "size_families_pt": pa.vtext.size_families,
                           "text_families": [{"family": k, "occurrences": v} for k, v in text_fams.most_common(20)],
                           "marks": len(pa.vtext.marks), "rejected_rows": len(pa.vtext.rejected_rows)},
        "annotation_structure": {"blocks": len(pa.blocks), "designation_grammar_families": [fam_stats(f) for f in sorted(des_fams, key=lambda f: -des_fams[f])],
                                 "grammar": pa.grammar.as_dict(), "leader_families": lfam_rows,
                                 "marker_families": [{"family": k, "occurrences": v} for k, v in marker_fams.most_common()],
                                 "dn_layouts": dict(Counter(d.dn_source or "none" for d in pa.designations))},
        "pipe_structure": {"representation_families": pipe_fams, "contact_votes": pa.contact_stats,
                           "junction_convention": "shared endpoints and endpoint-on-interior T contacts are nodes; crossings are never connections",
                           "hatched_areas": [h.as_dict() for h in pa.hatch_families]},
        "measurement": {"scale": pa.scale.as_dict(), "vertical_evidence": {"kind": "elevation annotations in label units", "anchors_with_elevation": len(pa.elevations)}},
        "unknown_structure": {"unsupported_families": unsupported,
                              "unresolved_anchor_reasons": dict(Counter(a.reason for a in pa.anchors if a.state != "VERIFIED_PIPE_ATTACHMENT"))},
    }


def _fmt(page):
    from ..measure.scale import _page_format
    return _page_format(page)


def profile_report_md(prof: dict, name: str) -> str:
    L = [f"# Drawing profile: {name}", "", f"Engine {prof['engine_version']}", "",
         "## Page structure", f"- size: {prof['page_structure']['width_pt']} x {prof['page_structure']['height_pt']} pt ({prof['page_structure']['format']}), rotation {prof['page_structure']['rotation']}, pages {prof['page_structure']['n_pages']}",
         "", "## CAD structure", f"- OCGs: {prof['cad_structure']['n_ocgs']}, layers with geometry: {prof['cad_structure']['n_layers_with_geometry']}, XObjects: {prof['cad_structure']['n_xobjects']}",
         f"- annotation layers (drawing-derived): {', '.join(sorted(prof['cad_structure']['annotation_layers'])) or 'none'}", "",
         "## Text structure", f"- searchable spans: {prof['text_structure']['searchable_spans']}, vector glyph rows: {prof['text_structure']['vector_glyph_rows']}, glyphs: {prof['text_structure']['glyphs']}, glyph families: {prof['text_structure']['glyph_families']} (unknown {prof['text_structure']['unknown_glyph_families']})",
         f"- glyph size families (pt): {prof['text_structure']['size_families_pt']}", "",
         "## Designation grammar families", "| pattern | occurrences | processed | confirmed | ambiguous | unsupported | examples |", "|---|---|---|---|---|---|---|"]
    for f in prof["annotation_structure"]["designation_grammar_families"]:
        L.append(f"| {f['family']} | {f['occurrences']} | {f['processed']} | {f['confirmed']} | {f['ambiguous']} | {f['unsupported']} | {', '.join(f['examples'])} |")
    L += ["", "## Leader families", "| family | occurrences | processed | confirmed | ambiguous | unsupported |", "|---|---|---|---|---|---|"]
    for f in prof["annotation_structure"]["leader_families"]:
        L.append(f"| {f['family']} | {f['occurrences']} | {f['processed']} | {f['confirmed']} | {f['ambiguous']} | {f['unsupported']} |")
    L += ["", "## Marker / connector families"] + [f"- {m['family']}: {m['occurrences']}" for m in prof["annotation_structure"]["marker_families"]]
    L += ["", "## Pipe representation families", "| family | kind | primitives | length pt | gap | confirmed | ambiguous | unowned |", "|---|---|---|---|---|---|---|---|"]
    for f in prof["pipe_structure"]["representation_families"]:
        L.append(f"| {f['family']} | {f['kind']} | {f['n_primitives']} | {f['total_length_pt']} | {f['gap_mode_pt']} | {f['confirmed']} | {f['ambiguous']} | {f['unowned']} |")
    sc = prof["measurement"]["scale"]
    L += ["", "## Scale", f"- state: {sc['state']} ({sc['reason']}), meters per PDF point: {sc['meters_per_pdf_point']}"]
    for e in sc["evidence"]:
        L.append(f"  - {e['kind']}: '{e['text']}' -> {e['meters_per_pt']} m/pt {e['detail']}")
    L += ["", "## Unsupported / unknown structure"]
    for u in prof["unknown_structure"]["unsupported_families"]:
        L.append(f"- {u['family']}: {u['kind']} ({u['occurrences']}; e.g. {', '.join(u['examples'])})")
    L.append(f"- unresolved anchor reasons: {prof['unknown_structure']['unresolved_anchor_reasons']}")
    return "\n".join(L) + "\n"


def evidence_graph(pa) -> dict[str, Any]:
    nodes = []
    edges = []
    def add(nid, kind, **attrs):
        nodes.append({"id": nid, "kind": kind, **attrs})
    des_by_id = {d.did: d for d in pa.designations}
    anc_by_id = {a.anchor_id: a for a in pa.anchors}
    ld_by_id = {l.lid: l for l in pa.leaders}
    for p in pa.ownership.pipes:
        add(p.physical_pipe_id, "PHYSICAL_PIPE", identity=p.identity.key, designation=p.identity.display, dn=p.identity.dn, length_pt=round(p.length_pt, 2), family=p.family)
        add(f"family:{p.family}", "DRAWING_FAMILY", family=p.family)
        edges.append({"from": f"family:{p.family}", "to": p.physical_pipe_id, "rel": "PIPE_GEOMETRY_OF"})
        for seg in p.source_segments[:50]:
            add(f"raw:{seg}", "RAW_PDF_OBJECT", segment=seg)
            edges.append({"from": f"raw:{seg}", "to": p.physical_pipe_id, "rel": "SOURCE_OF"})
        for aid in p.anchor_ids:
            a = anc_by_id.get(aid)
            if not a:
                continue
            add(aid, "PIPE_ATTACHMENT", state=a.state, endpoint=list(a.endpoint))
            edges.append({"from": aid, "to": p.physical_pipe_id, "rel": "OWNS"})
            d = des_by_id.get(a.designation_id)
            if d:
                add(d.did, "DESIGNATION", text=d.text, dn=d.dn, source=d.source, bbox=list(d.bbox))
                edges.append({"from": d.did, "to": aid, "rel": "LABELS"})
                for pid in d.tokens and []:
                    pass
                for prov in sorted(set(sum([g.path_ids for g in [] ], [])))[:0]:
                    pass
            ld = ld_by_id.get(a.leader_id)
            if ld:
                add(ld.lid, "ACTUAL_LEADER", family=ld.family, paths=ld.path_ids, endpoint=list(ld.end))
                edges.append({"from": d.did if d else aid, "to": ld.lid, "rel": "HAS_LEADER"})
                edges.append({"from": ld.lid, "to": aid, "rel": "ENDS_AT"})
                for pid in ld.path_ids:
                    add(f"raw:{pid}", "RAW_PDF_OBJECT", path=pid)
                    edges.append({"from": f"raw:{pid}", "to": ld.lid, "rel": "SOURCE_OF"})
        add("scale", "SCALE", **pa.scale.as_dict())
        edges.append({"from": "scale", "to": p.physical_pipe_id, "rel": "MEASURES"})
    # dedupe nodes
    seen = {}
    for n in nodes:
        seen.setdefault(n["id"], n)
    return {"nodes": list(seen.values()), "edges": edges}


def why(pa, pipe_id: str) -> dict[str, Any]:
    p = next((x for x in pa.ownership.pipes if x.physical_pipe_id == pipe_id), None)
    if p is None:
        return {"error": "unknown pipe id", "pipe_id": pipe_id}
    anc = [a for a in pa.anchors if a.anchor_id in p.anchor_ids]
    des = {d.did: d for d in pa.designations}
    lds = {l.lid: l for l in pa.leaders}
    chain = []
    for a in anc:
        d = des.get(a.designation_id)
        ld = lds.get(a.leader_id)
        b = next((b for b in pa.blocks if b.bid == a.block_id), None)
        chain.append({
            "designation": d.as_dict() if d else None,
            "glyph_or_text_evidence": {"source": d.source if d else None, "provenance_paths": (next((r.line.provenance for r in b.rows if r.line.rid and d and r.line.bbox == d.bbox), [])[:40] if b and d else [])},
            "dn": {"value": a.dn, "source": d.dn_source if d else None},
            "leader": ld.as_dict() if ld else None,
            "attachment": a.as_dict(),
        })
    m = next((m for m in pa.measures if m.pipe.physical_pipe_id == pipe_id), None)
    from ..pipes.ownership import DECLARED_REASON
    declared = None
    if DECLARED_REASON in (p.evidence or []):
        # no label reached this run: the sheet's own written rule named it, and that rule is the evidence
        declared = {"rule": pa.declarations.as_dict(),
                    "text": "Ingen etikett når den här sträckan. Bladet skriver att kopplingsledningar från fördelare "
                            "till apparat följer tabellen om inget annat anges, och tabellen ger "
                            f"{p.identity.display}; sträckan ligger på ett lager som bär systemet {p.identity.system}."}
    return {"pipe_id": pipe_id, "identity": p.identity.key, "designation": p.identity.display, "dn": p.identity.dn, "family": p.family,
            "evidence_chain": chain, "declared_by_sheet": declared,
            "topology": {"nodes": p.nodes, "primitives": len(p.prim_ids), "evidence": p.evidence},
            "source_paths": p.source_paths, "source_segments": p.source_segments,
            "scale": pa.scale.as_dict(),
            "measurement": {"horizontal_pdf_units": round(p.length_pt, 3), "raw_pt": round(p.raw_length_pt, 3), "bridged_gap_pt": round(p.bridged_gap_pt, 3),
                            "horizontal_m": m.horizontal_m if m else None, "vertical_m": m.vertical_m if m else None,
                            "vertical_evidence": m.vertical_evidence if m else None, "state": m.state if m else None}}


def unresolved_issues(pa) -> list[dict]:
    issues = []
    # Unknown glyph shapes: hundreds of one-line entries drown the list, and most sit in legend text or notes that
    # never reach the takeoff. Report one entry for the shapes that break a designation and one for the rest.
    unknown_fams = [f for f in pa.vtext.families.values() if f.char == "?" and f.n_members >= 2]
    if unknown_fams:
        in_designation = sum(d.unknown_chars for d in pa.designations)
        total = sum(f.n_members for f in unknown_fams)
        if in_designation:
            first = next((d for d in pa.designations if d.unknown_chars), None)
            issues.append({"kind": "unknown_glyph_in_designation", "count": in_designation,
                           "families": len(unknown_fams), "bbox": list(first.bbox) if first else None,
                           "reason": "tecken som inte kunde namnges sitter i en beteckning och gör den oläsbar"})
        rest = total - in_designation
        if rest > 0:
            issues.append({"kind": "unknown_glyph_elsewhere", "count": rest, "families": len(unknown_fams),
                           "reason": "tecken som inte kunde namnges i legend, noter eller ramtext; påverkar inte mängden"})
    # The unresolved list is for what could still change a metre. A sheet's own designation list is not a set of
    # labels that failed - its rows sit in the legend block, name a code rather than a run, and will never carry
    # a dimension or a leader. Counting them buried the handful of real failures under a hundred false ones.
    lg = pa.legend
    lbox = lg.bbox()
    components = lg.components()

    def _in_legend(d) -> bool:
        if lbox is None:
            return False
        cx, cy = (d.bbox[0] + d.bbox[2]) / 2, (d.bbox[1] + d.bbox[3]) / 2
        return lbox[0] - 2 <= cx <= lbox[2] + 2 and lbox[1] - 2 <= cy <= lbox[3] + 2

    # A pipe identity is made of two things the drawing has to supply: the size the sheet writes, and a real line
    # from the label to the geometry. A candidate with neither has supplied nothing at all - it is a drawing
    # number in the title block, a door mark, a template placeholder - and reporting it as a pipe that failed
    # fills the list a reader works through with text that was never a pipe. Seven such texts on one A1 sheet
    # produced fourteen blocking rows, which is the whole list.
    blocks_with_a_leader = {ld.block_id for ld in pa.leaders}

    def _has_any_evidence(d) -> bool:
        return d.dn is not None or d.block_id in blocks_with_a_leader

    def _could_be_a_pipe_label(d) -> bool:
        text = (d.text or "").upper()
        return (lg.names_a_pipe(d) and text not in components and _has_any_evidence(d)
                and not lg.names_a_component(text) and not _in_legend(d))

    for d in pa.designations:
        if d.unknown_chars:
            issues.append({"kind": "uncertain_designation", "text": d.text, "bbox": list(d.bbox), "id": d.did})
        elif d.dn is None and _could_be_a_pipe_label(d):
            issues.append({"kind": "missing_dn", "text": d.text, "bbox": list(d.bbox), "id": d.did})
    with_leader = {a.designation_id for a in pa.anchors}
    # why a label has no leader is the difference between "the draughtsman drew none" and "the reading lost it",
    # and only one of those is the reading's to fix. It is the commonest way a pipe the sheet names goes unmarked.
    no_leader = (pa.contact_stats or {}).get("labels_without_a_leader") or {}
    for d in pa.designations:
        if d.did not in with_leader and _could_be_a_pipe_label(d):
            issues.append({"kind": "missing_leader", "text": d.text, "bbox": list(d.bbox), "id": d.did,
                           "reason": ", ".join(no_leader.get(d.block_id) or []) or None})
    by_did = {d.did: d for d in pa.designations}
    for a in pa.anchors:
        d = by_did.get(a.designation_id)
        if d is not None and not _could_be_a_pipe_label(d):
            continue        # a fitting tag whose leader lands on the run it connects to is not a failure
        if a.evidence.get("closed_on_owned_run"):
            continue        # the drawing repeating a name over a run it already named
        if a.state == "AMBIGUOUS_PIPE_ATTACHMENT":
            issues.append({"kind": "ambiguous_pipe_attachment", "text": a.designation, "reason": a.reason, "bbox": [a.endpoint[0] - 5, a.endpoint[1] - 5, a.endpoint[0] + 5, a.endpoint[1] + 5], "id": a.anchor_id})
        elif a.state == "NO_PIPE_ATTACHMENT":
            issues.append({"kind": "missing_pipe_attachment", "text": a.designation, "reason": a.reason, "bbox": [a.endpoint[0] - 5, a.endpoint[1] - 5, a.endpoint[0] + 5, a.endpoint[1] + 5], "id": a.anchor_id})
    for r in pa.ownership.ambiguous_runs:
        # An unresolved case is the least important thing in a reading and must never cost the reading itself.
        # A record naming a family or a primitive this graph does not hold is a defect worth seeing, not a
        # reason to lose the whole analysis, so it is reported without a place on the sheet.
        g = pa.graphs.get(r.get("family"))
        prim = g.prims.get(r.get("from_prim")) if g is not None else None
        s = prim.seg if prim is not None else None
        kind = {"AMBIGUOUS_DN_BOUNDARY": "dn_conflict",
                "AMBIGUOUS_SLIVER_PAIR_READS_AS_A_DRAWN_OUTLINE": "drawn_outline",
                "AMBIGUOUS_FLOW_BEYOND_THE_LABELLED_RUNS": "flow_beyond_labels"}.get(r["reason"], "topology_conflict")
        issues.append({"kind": kind, "reason": r["reason"], "identities": r.get("identities", []),
                       "bbox": ([s.x0 - 5, s.y0 - 5, s.x1 + 5, s.y1 + 5] if s is not None else None),
                       "id": f"run:{r.get('family')}:{r.get('from_prim')}"})
    # branch conflicts + unowned geometry (aggregate per family chain)
    for fk, sts in pa.ownership.prim_states.items():
        g = pa.graphs[fk]
        branch = [pid for pid, st in sts.items() if st.state == "AMBIGUOUS" and st.reason == "AMBIGUOUS_BRANCH"]
        if branch:
            pid = branch[0]; s = g.prims[pid].seg
            issues.append({"kind": "branch_conflict", "family": fk, "count": len(branch), "bbox": [s.x0 - 5, s.y0 - 5, s.x1 + 5, s.y1 + 5], "id": f"branch:{fk}"})
        un = [pid for pid, st in sts.items() if st.state == "UNOWNED"]
        if un:
            L = sum(g.prims[p].seg.length for p in un)
            pid = un[0]; s = g.prims[pid].seg
            issues.append({"kind": "unowned_geometry", "family": fk, "count": len(un), "length_pt": round(L, 1), "bbox": [s.x0 - 5, s.y0 - 5, s.x1 + 5, s.y1 + 5], "id": f"unowned:{fk}"})
    if pa.scale.state in ("NONE", "CONFLICT"):
        issues.append({"kind": "unsupported_structural_family", "text": f"scale: {pa.scale.reason}", "id": "scale"})
    # What the reading did about the sheet's vocabulary, said out loud. Without a designation list nothing is
    # claimed about what any code means - every label speaks for itself and no code is set aside as a fitting -
    # and that is a different reading from one governed by a list, so it should not have to be inferred from a
    # count. Where the list came off another sheet of the set, that is worth saying for the same reason.
    if not lg.entries:
        issues.append({"kind": "no_designation_list", "id": "legend",
                       "reason": "ingen beteckningslista hittades, varken på bladet eller på något annat blad i "
                                 "handlingen; läsningen gör därför inga anspråk på vad koderna betyder och sätter "
                                 "ingen kod åt sidan som komponent"})
    elif not lg.own:
        pages = sorted({e.page for e in lg.entries if e.page is not None})
        issues.append({"kind": "designation_list_from_another_sheet", "id": "legend",
                       "reason": "bladet bär ingen egen beteckningslista; handlingens lista "
                                 + (f"på blad {', '.join(str(p + 1) for p in pages)} " if pages else "")
                                 + "gäller här, och får bara neka en kod den själv listar"})
    # A measured name elsewhere on the sheet does not resolve this label. Only
    # the label's own anchor on a measured physical pipe supplies that evidence.
    measured_anchors = {aid for m in pa.measures
                        if m.total_m is not None and m.total_m > 0
                        for aid in m.pipe.anchor_ids}
    resolved_labels = {a.designation_id for a in pa.anchors
                       if a.anchor_id in measured_anchors or a.evidence.get("closed_on_owned_run")}
    blocking_kinds = {"missing_pipe_attachment", "ambiguous_pipe_attachment",
                      "missing_leader", "missing_dn", "uncertain_designation"}
    for it in issues:
        resolved = (it.get("id") in resolved_labels
                    and it["kind"] in {"missing_dn", "missing_leader"})
        it["severity"] = "blocking" if it["kind"] in blocking_kinds and not resolved else "advisory"
        if resolved:
            it["note"] = "etikettens egen hänvisning är kopplad till en uppmätt rörsträcka"
    return issues


DECLINED_WHY = {
    "NO_CONTINUOUS_RUN": "korta lösa streck, ingen sammanhängande sträcka",
    "FAINTEST_PEN_ON_THE_SHEET": "ritningens tunnaste penna utan lagernamn - bakgrund",
    "NO_LABEL_REACHED_IT": "ingen rörbeteckning når fram till den",
    "NO_LEADER_EVER_CAME_NEAR_IT": "ingen ledare kom i närheten - läsningen vägde den aldrig",
    "ON_A_LAYER_THE_READING_TREATS_AS_ANNOTATION": "på ett lager läsningen behandlar som text och ramar",
    "A_LABEL_POINTED_AT_IT_AND_IT_WAS_NOT_TAKEN": "en etikett pekade hit, men pennan togs inte som rör",
    "IT_RUNS_FROM_A_LABEL_BLOCK": "hänvisningslinjer - strecken går från bladets egna etiketter, inte genom byggnaden",
}


def declined_geometry(pa) -> dict[str, Any]:
    """The drawn families the reading looked at and did not take, with their strokes and the reason.

    A declined family is simply absent from everything downstream, and geometry that disappears without a word
    looks exactly like geometry that was never seen. Most declines are right - a wall shares a pen with a pipe -
    so this is not a list of mistakes. It is the reading saying which ink it decided was not pipe, so that a
    reader looking at un-measured lines on the sheet can see the reason instead of guessing at one.
    """
    mpp = pa.scale.meters_per_pt if pa.scale else None
    dec = (pa.contact_stats or {}).get("declined_families") or {}
    fams = []
    for f in sorted(dec, key=lambda k: (-dec[k]["tick_votes"], -dec[k]["votes"], -dec[k]["total_length_pt"])):
        v = dec[f]
        layer, _, style = f.partition("|s|")
        fams.append({"family": f, "layer": layer, "style": style, "kind": v["kind"], "why": v["why"],
                     "why_sv": DECLINED_WHY.get(v["why"], v["why"]), "width": v["width"],
                     "longest_chain_pt": v["longest_chain"], "length_pt": v["total_length_pt"],
                     "length_m": round(v["total_length_pt"] * mpp, 2) if mpp else None,
                     "n_segments": v["n_segments"], "leader_ends_touching": v["tick_votes"],
                     "label_votes": v["votes"], "segments": v.get("segments") or [],
                     "segments_truncated": bool(v.get("segments_truncated"))})
    unc = (pa.contact_stats or {}).get("unconsidered_families") or {}
    never = []
    for f in sorted(unc, key=lambda k: -unc[k]["total_length_pt"]):
        v = unc[f]
        layer, _, style = f.partition("|s|")
        never.append({"family": f, "layer": layer, "style": style, "kind": "not_examined", "why": v["why"],
                      "why_sv": DECLINED_WHY.get(v["why"], v["why"]), "width": v["width"],
                      "longest_chain_pt": None, "length_pt": v["total_length_pt"],
                      "length_m": round(v["total_length_pt"] * mpp, 2) if mpp else None,
                      "n_segments": v["n_segments"], "leader_ends_touching": 0, "label_votes": 0.0,
                      "on_a_pipe_like_layer": bool(v.get("on_a_pipe_like_layer")),
                      "segments": v.get("segments") or [], "segments_truncated": bool(v.get("segments_truncated"))})
    # where the drawing drew the same line twice. It is reported rather than subtracted, and the reason is
    # measured: see duplicate_overlaps.
    dt = (pa.contact_stats or {}).get("drawn_twice") or {}
    drawn_twice = {"n_places": dt.get("n_places", 0), "length_m": round(dt.get("total_pt", 0.0) * mpp, 2) if mpp else None,
                   "places": [{**d, "m": round(d["pt"] * mpp, 3) if mpp else None} for d in (dt.get("places") or [])]}
    return {"families": fams, "unconsidered": never, "drawn_twice": drawn_twice,
            "totals": {"families": len(fams), "segments": sum(f["n_segments"] for f in fams),
                       "segments_carried": sum(len(f["segments"]) for f in fams),
                       "length_m": round(sum(f["length_pt"] for f in fams) * mpp, 2) if mpp else None,
                       "length_m_with_a_leader_end": round(sum(f["length_pt"] for f in fams if f["leader_ends_touching"]) * mpp, 2) if mpp else None,
                       "unconsidered_families": len(never), "unconsidered_segments": sum(f["n_segments"] for f in never),
                       "unconsidered_segments_carried": sum(len(f["segments"]) for f in never),
                       "unconsidered_length_m": round(sum(f["length_pt"] for f in never) * mpp, 2) if mpp else None,
                       "unconsidered_length_m_on_a_pipe_like_layer": round(sum(f["length_pt"] for f in never if f["on_a_pipe_like_layer"]) * mpp, 2) if mpp else None,
                       "filled_shapes": (pa.contact_stats or {}).get("filled_shapes"),
                       "filled_shapes_length_m": (round(((pa.contact_stats or {}).get("filled_shapes") or {}).get("length_pt", 0.0) * mpp, 2) if mpp else None)}}


def document_quantities(sheets: list[dict]) -> dict[str, Any]:
    """The takeoff for the whole set, sheet by sheet and added up.

    A set of drawings is one building, and an estimator prices the building. Reading every sheet and then
    reporting the first one measures the ground floor of a block of flats and calls it the block: the other
    sheets were read, drawn onto the overlays, and then dropped on the floor. Here every sheet keeps its own
    rows, so a designation can be followed from sheet to sheet, and the same rows are added up per designation
    so there is a figure for the building.

    Every sheet's metres are added up, and the sheets that did not settle their own scale are named. A sheet
    whose stamp and scale bar disagree, or that borrowed the set's scale, was still measured - dropping it would
    answer a question nobody asked - but its metres are a proposal, so they are counted separately as well as in
    the sum, and the sheet is listed by page. What the reader must be able to see is how much of the building's
    total rests on a scale the drawing itself never settled.
    """
    rows: dict[tuple, dict] = {}
    unscaled = []
    unsettled_m = 0.0
    for sh in sheets:
        if (sh.get("scale") or {}).get("state") not in SETTLED_SCALE:
            unscaled.append({"page": sh.get("page"), "state": (sh.get("scale") or {}).get("state"),
                             "reason": (sh.get("scale") or {}).get("reason")})
            unsettled_m += sum(float(q.get("confirmed_total_m") or 0.0) for q in sh.get("quantities") or [])
        for q in sh.get("quantities") or []:
            key = (q.get("designation"), q.get("dn"))
            r = rows.setdefault(key, {"designation": q.get("designation"), "base": q.get("base"), "dn": q.get("dn"),
                                      "sheets": [], "pipe_ids": [], "label_count": 0, "physical_pipe_count": 0,
                                      "confirmed_horizontal_m": 0.0, "confirmed_vertical_m": 0.0,
                                      "confirmed_total_m": 0.0, "ambiguous_m": 0.0, "review_m": 0.0, "in_hatched_area_m": 0.0,
                                      "unnamed_review_m": 0.0, "proposed_review_m": 0.0, "state": q.get("state"),
                                      "riser_count": 0, "riser_count_from_labels": 0})
            r["sheets"].append(sh.get("page"))
            if q.get("riser_height_m") is not None:
                r["riser_height_m"] = q["riser_height_m"]
            r["riser_slab_count"] = r.get("riser_slab_count", 0) + int(q.get("riser_slab_count") or 0)
            # the runs behind the row, sheet by sheet: a set's figure has to lead back to the ink like a sheet's
            r["pipe_ids"].extend(q.get("pipe_ids") or [])
            # both riser readings travel with the row: the takeoff chooses between them, and a rollup that
            # carried only one of them would answer a question the reader did not ask
            for k in ("label_count", "physical_pipe_count", "riser_count", "riser_count_from_labels"):
                r[k] += int(q.get(k) or 0)
            for k in ("confirmed_horizontal_m", "confirmed_vertical_m", "confirmed_total_m", "ambiguous_m",
                      "in_hatched_area_m", "review_m", "unnamed_review_m", "proposed_review_m"):
                r[k] += float(q.get(k) or 0.0)
    out_rows = []
    for r in sorted(rows.values(), key=lambda r: (r["designation"] or "", r["dn"] if r["dn"] is not None else -1)):
        out_rows.append({**r, "sheets": sorted(set(r["sheets"])), "pipe_ids": sorted(set(r["pipe_ids"])),
                         **{k: round(r[k], 2) for k in ("confirmed_horizontal_m", "confirmed_vertical_m",
                                                        "confirmed_total_m", "ambiguous_m", "in_hatched_area_m", "review_m",
                                                        "unnamed_review_m", "proposed_review_m")}})
    totals = {k: round(sum(r[k] for r in out_rows), 2)
              for k in ("confirmed_horizontal_m", "confirmed_vertical_m", "confirmed_total_m", "ambiguous_m",
                        "in_hatched_area_m", "review_m", "unnamed_review_m", "proposed_review_m")}
    totals.update({"m_under_an_unsettled_scale": round(unsettled_m, 2),
                   "designations": len(out_rows), "sheets": len(sheets),
                   "physical_pipes": sum(r["physical_pipe_count"] for r in out_rows),
                   "riser_count": sum(r["riser_count"] for r in out_rows),
                   "riser_count_from_labels": sum(r["riser_count_from_labels"] for r in out_rows)})
    return {"totals": totals, "rows": out_rows, "sheets": sheets, "sheets_without_a_settled_scale": unscaled}


# The names of what one sheet's reading is written down as. Every one of them is about a single sheet, so on a
# set each sheet gets its own copy under sheets/<page>/ and the reader is served the sheet they are looking at.
_TAG_LIKE = re.compile(r"(?<![A-Za-z0-9])[A-ZÅÄÖ]{1,5}\d{2,4}[A-Z]?(?![A-Za-z])")

SHEET_FILES = ("vector-designations.json", "component-tags.json", "leader-forensics.json", "leader-family-report.json",
               "pipe-code-anchors.json", "pipe-representation-families.json", "pipe-geometry-inventory.json",
               "drawn-system-families.json", "declined-geometry.json", "pipe-topology.json",
               "physical-pipes.json", "review-pipes.json", "pipe-extent-frontiers.json", "quantities.json",
               "unresolved-issues.json", "evidence-graph.json", "reconciliation.json",
               "coverage-validity.json", "route-crosscheck.json", "reading-review.json",
               "drawing-legend.json", "drawing-declarations.json", "cad-layer-map.json", "page.json",
               "drawing-style.json", "pdf-visibility.json")


def sheet_reading(pa, doc, doc_legend=None, profile: dict | None = None,
                  forensics: bool = True) -> dict[str, Any]:
    """Everything one sheet's reading says, as the files it is written down as.

    A set of drawings is read sheet by sheet and each sheet is let go of as soon as it has been used, so that a
    fifty-sheet set does not need fifty readings' worth of geometry at once. That is why this exists: the sheet
    is written down here, while it is still in hand, instead of being kept in memory until the end. Reporting
    only the sheet that happened to be kept would show the reader an empty first page and hide the twenty-five
    pipes drawn behind it.

    What comes back is the sheet alone - its pipes, its labels, its leaders, its ink and what was decided about
    each piece of it. The set-wide answers (the takeoff summed over sheets, the coverage per sheet, the shared
    designation list) are not in here, because they are not facts about one sheet.
    """
    from ..profile.hatch import inside_hatch
    prof = profile if profile is not None else drawing_profile(pa, doc)
    out: dict[str, Any] = {"page.json": {"page": pa.page.info.index, **prof["page_structure"]}}
    from ..profile.styles import identify
    out["drawing-style.json"] = identify(pa.page)
    out["pdf-visibility.json"] = {"page": pa.page.info.index, **pa.page.visibility_report}

    def _in_wall(x: float, y: float) -> bool:
        return bool(pa.hatch_families) and inside_hatch(pa.hatch_families, x, y) is not None

    out["cad-layer-map.json"] = {"layers": [{"layer": k, **v.as_dict(), "role": next((l["role"] for l in prof["cad_structure"]["layers"] if l["layer"] == k), "UNKNOWN")} for k, v in sorted(pa.layer_stats.items())],
                                 "annotation_layers": pa.ann_layers, "pipe_families": sorted(pa.pipe_families)}
    des_out = []
    for d in pa.designations:
        dd = d.as_dict()
        dd["in_wall"] = _in_wall((d.bbox[0] + d.bbox[2]) / 2, (d.bbox[1] + d.bbox[3]) / 2)
        dd["names_a_pipe"] = bool(pa.legend.names_a_pipe(d)) and (d.text or "").upper() not in pa.legend.components()
        des_out.append(dd)
    # The sheet's whole text layer, every row of it, is a forensic record: nothing that serves a reader reads
    # it, and on a set it is by far the largest thing written - twenty-six copies of it is ninety per cent of a
    # reading's disk for something no page of the application opens. It is written once, with the sheet the
    # profile report is about, and the per-sheet copies carry the labels alone.
    out["vector-designations.json"] = {"designations": des_out,
                                       **({"text_rows": [r.as_dict() for r in pa.lines]} if forensics else {})}
    # Komponentkoderna på bladet (RB201, SIL501, VVB01, RV602-20): textraderna som bär en kod, med var de står.
    # Litet nog för varje blad, och det som "mängder från ritning" räknar komponenter på (vvs_engine.tb.drawing_link).
    out["component-tags.json"] = {"rows": [{"text": r.text, "bbox": [round(float(x), 1) for x in r.bbox],
                                            "page": r.page} for r in pa.lines if _TAG_LIKE.search(r.text or "")]}
    # The set's list, but told from this sheet: whether the sheet in front of the reader is the one that wrote
    # the list is a fact about this sheet, and the set-wide copy is marked borrowed for everybody by construction.
    _lg = doc_legend if doc_legend is not None and doc_legend.entries else pa.legend
    out["drawing-legend.json"] = {**_lg.as_dict(), "own": pa.legend.own and bool(pa.legend.entries),
                                  "usage_systems": pa.legend.usage_systems}
    out["drawing-declarations.json"] = pa.declarations.as_dict()
    lead_out = []
    for l in pa.leaders:
        ld = l.as_dict()
        ld["in_wall"] = _in_wall(*l.end)
        lead_out.append(ld)
    out["leader-forensics.json"] = {"leaders": lead_out}
    out["leader-family-report.json"] = leader_family_report(pa.leaders)
    names_pipe = {d["did"]: d["names_a_pipe"] for d in des_out}
    anc_out = []
    for a in pa.anchors:
        ad = a.as_dict()
        ad["in_wall"] = _in_wall(*a.endpoint)
        ad["names_a_pipe"] = bool(names_pipe.get(a.designation_id, False))
        anc_out.append(ad)
    out["pipe-code-anchors.json"] = {"anchors": anc_out}
    out["pipe-representation-families.json"] = {"families": [rf.as_dict() for rf in pa.pipe_families.values()]}
    # Which unowned lines a label actually points at. Not a measurement - nothing here settles anything - but a
    # line the sheet plainly draws and plainly labels must not be filed with the ink nobody mentioned.
    from ..pipeline import claimed_runs
    claimed = claimed_runs(pa.anchors, pa.ownership, pa.graphs)
    inv = []
    for fk, g in pa.graphs.items():
        for pid, q in g.prims.items():
            st = pa.ownership.prim_states[fk][pid]
            by = (claimed.get(fk) or {}).get(pid) or []
            inv.append({"family": fk, "prim": pid, "pid": q.pid, "seg": q.seg_index, "x0": round(q.seg.x0, 2), "y0": round(q.seg.y0, 2), "x1": round(q.seg.x1, 2), "y1": round(q.seg.y1, 2),
                        "length": round(q.seg.length, 3), "state": st.state, "identity": st.identity.key if st.identity else None,
                        "candidates": sorted(c.key for c in st.candidates), "reason": st.reason,
                        "claimed_by": sorted(by),
                        "in_hatch": bool(pa.hatch_families) and inside_hatch(pa.hatch_families, *q.seg.mid) is not None})
    out["pipe-geometry-inventory.json"] = {"primitives": inv}
    # What this sheet states about which pen its office draws which system with. A label verified on a run says
    # it outright; nothing here is inferred. It is written down so the next sheet of the same project can use it
    # where its own bundles are symmetric - one drawing telling another, with no reader in between.
    states: Counter = Counter()
    for a in pa.anchors:
        if a.state != "VERIFIED_PIPE_ATTACHMENT" or not a.system_token:
            continue
        # Inferred bundle/family/AI decisions must not train their own next decision.
        if a.evidence.get("bundle") or any(w in a.reason for w in ("settled", "consistency", "elimination", "family_this_sheet", "second_reader")):
            continue
        for family in {c.family for c in a.contacts if c.family.split("|s|")[0]}:
            states[(family, a.system_token.upper())] += 1
    out["drawn-system-families.json"] = {"version": 2, "evidence_kind": "direct_local_anchors",
        "stated": [{"family": f, "system": sy, "times": n} for (f, sy), n in states.most_common()]}
    out["declined-geometry.json"] = declined_geometry(pa)
    out["pipe-topology.json"] = {"families": [{"family": fk, "nodes": [{"id": n.nid, "x": round(n.x, 2), "y": round(n.y, 2), "degree": n.degree, "prims": n.prims} for n in g.nodes.values()],
                                               "edges": [{"prim": pid, "a": ab[0], "b": ab[1]} for pid, ab in g.prim_nodes.items()], "bridges": g.bridges, "junctions": g.junctions, "gap_mode": g.gap_mode}
                                              for fk, g in pa.graphs.items()]}
    # the reading's own pipes, and apart from them what it measured for review (include_for_review): the agent,
    # corrections and learned rules work on the reading's pipes, and the viewer draws both
    from ..pipes.ownership import BEST_READING_REASON, UNNAMED_REASON
    def _for_review(m) -> bool:
        ev = m.pipe.evidence or []
        return UNNAMED_REASON in ev or BEST_READING_REASON in ev
    out["physical-pipes.json"] = {"physical_pipes": [physical_pipe_dict(m) for m in pa.measures if not _for_review(m)]}
    out["review-pipes.json"] = {"review_pipes": [physical_pipe_dict(m) for m in pa.measures if _for_review(m)]}
    out["pipe-extent-frontiers.json"] = extent_frontiers(pa)
    out["quantities.json"] = {"scale": pa.scale.as_dict(), "rows": pa.quantities,
                              "totals": {"physical_pipes": len(pa.measures),
                                         "confirmed_horizontal_m": round(sum(q["confirmed_horizontal_m"] for q in pa.quantities), 3),
                                         "confirmed_vertical_m": round(sum(q["confirmed_vertical_m"] for q in pa.quantities), 3),
                                         "confirmed_total_m": round(sum(q["confirmed_total_m"] for q in pa.quantities), 3),
                                         "ambiguous_m": round(sum(q["ambiguous_m"] for q in pa.quantities), 3),
                                         "review_m": round(sum(q.get("review_m", 0.0) for q in pa.quantities), 3),
                                         "in_hatched_area_m": round(sum(q.get("in_hatched_area_m", 0.0) for q in pa.quantities), 3),
                                         "riser_labels": sum(q.get("riser_count", 0) for q in pa.quantities)},
                              "hatched_areas": [h.as_dict() for h in pa.hatch_families],
                              "risers": pa.risers}
    out["unresolved-issues.json"] = {"issues": unresolved_issues(pa)}
    out["evidence-graph.json"] = evidence_graph(pa)
    from ..reconcile import reconcile
    rec = reconcile(pa)
    out["reconciliation.json"] = rec
    # giltigheten är en annan fråga än konserveringen: nådde läsningen bladet?
    from ..coverage import coverage_validity, completion_checks
    from ..pipeline import reading_coverage as _rc
    out["coverage-validity.json"] = coverage_validity(_rc(pa), pa.anchors, rec, pa.scale.state if pa.scale else None,
                                                      len(pa.measures))
    out["coverage-validity.json"] = completion_checks(out["coverage-validity.json"], pa.quantities,
        getattr(pa, "source_assignment", None), pa.review_findings, from_image=_from_image(pa))
    out["route-crosscheck.json"] = pa.crosscheck
    out["reading-review.json"] = pa.review_findings
    if getattr(pa, "source_assignment", None) is not None:
        out["source-assignment.json"] = pa.source_assignment
    return out


def write_sheet(pa, doc, out_dir: str, doc_legend=None) -> str:
    """One sheet's reading, written down under sheets/<page>/ while the sheet is still in hand."""
    d = os.path.join(out_dir, "sheets", str(pa.page.info.index))
    os.makedirs(d, exist_ok=True)
    for fn, obj in sheet_reading(pa, doc, doc_legend, forensics=False).items():
        _dump(os.path.join(d, fn), obj)
    return d


def write_all(pdf_path: str, doc, analyses: list, out_dir: str, name: str, timings: dict, determinism: dict | None,
              contamination: dict | None, overlays: dict, config: dict, review: dict | None = None,
              sheets: list[dict] | None = None, doc_legend=None) -> dict[str, str]:
    os.makedirs(out_dir, exist_ok=True)
    pa = analyses[0]
    files: dict[str, str] = {}
    def W(fn, obj):
        path = os.path.join(out_dir, fn); _dump(path, obj); files[fn] = path
    prof = drawing_profile(pa, doc)
    W("drawing-profile.json", prof)
    with open(os.path.join(out_dir, "drawing-profile-report.md"), "w", encoding="utf-8") as fh:
        fh.write(profile_report_md(prof, name))
    files["drawing-profile-report.md"] = os.path.join(out_dir, "drawing-profile-report.md")
    W("raw-vector-inventory.json", doc.inventory())
    W("document-quantities.json", document_quantities(sheets or []))
    # How much of what the drawing names the reading carried through to a metre. It is the only figure that
    # tells a sheet the reading got through from a sheet it barely opened, so it is written down as its own
    # artifact rather than left to be worked out from a count of review rows.
    W("reading-coverage.json", {"sheets": [{"page": sh.get("page"), **(sh.get("coverage") or {})}
                                           for sh in (sheets or [])]} if sheets
      else {"sheets": [{"page": pa.page.info.index, **reading_coverage(pa)}]})
    # Varje beteckning bladet skriver, med slag, platser och mängd - bara i läget "Alla" (register.py). En
    # VVS-läsning skriver inte filen alls.
    registers = [{"page": sh.get("page"), **sh["register"]} for sh in (sheets or []) if sh.get("register")] \
        if sheets else ([{"page": pa.page.info.index, **pa.register}] if getattr(pa, "register", None) else [])
    if registers:
        W("all-designations.json", {"sheets": registers})
    # This sheet's own reading, written down once. The same shape is written per sheet under sheets/<page>/ by
    # write_sheet as each sheet is read, so a set is served the sheet the reader is looking at rather than
    # whichever sheet happened to be kept in memory.
    for _fn, _obj in sheet_reading(pa, doc, doc_legend, profile=prof).items():
        if _fn != "page.json":
            if _fn == "coverage-validity.json":
                from ..coverage import completion_checks
                _obj = completion_checks(_obj, pa.quantities, getattr(pa, "source_assignment", None), review,
                                         from_image=_from_image(pa))
            W(_fn, _obj)
    if review is not None:
        W("review-findings.json", review)
    if getattr(pa, "ocr_assist", None) is not None:
        W("ocr-assisted-characters.json", pa.ocr_assist)

    if determinism is not None:
        W("determinism.json", determinism)
    if contamination is not None:
        W("contamination-report.json", contamination)
    W("performance-report.json", performance_report(pa, timings))
    for k, v in overlays.items():
        files[k] = v
    with open(os.path.join(out_dir, "analysis-report.md"), "w", encoding="utf-8") as fh:
        fh.write(analysis_report_md(pa, name, timings, determinism, contamination, files))
    files["analysis-report.md"] = os.path.join(out_dir, "analysis-report.md")
    # freeze manifest
    from ..build import engine_digest
    manifest = {"state": "BLIND_FROZEN", "drawing": name, "input_pdf_sha256": _sha(pdf_path), "source_revision": source_revision(),
                "engine_source_sha256": engine_digest(),
                "engine_version": __version__, "artifact_schema": ARTIFACT_SCHEMA, "configuration": config, "python": platform.python_version(), "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "artifacts": {fn: _sha(path) for fn, path in sorted(files.items())}}
    W("freeze-manifest.json", manifest)
    return files


def extent_frontiers(pa) -> dict[str, Any]:
    """Var varje rör slutar och varför (uppdragets pipe_extent_frontiers): skälen, varje front, och summan.

    `silent_pipes` ska vara tom. Är den inte det har ett rör lämnat läsningen utan kant, och det är ett fel i
    läsningen - inte i ritningen."""
    from ..pipes.frontier import Frontier, REASONS, REAL, LOSSY, OPEN, summary
    fs = [Frontier(d["pipe"], d["family"], d["node"], d["x"], d["y"], d["reason"], d["detail"]) for d in pa.frontiers]
    mpp = pa.scale.meters_per_pt if pa.scale and pa.scale.meters_per_pt else None
    sm = summary(fs, pa.ownership.pipes if pa.ownership else [], mpp)
    ident = {p.physical_pipe_id: p.identity for p in (pa.ownership.pipes if pa.ownership else [])}
    rows = []
    for d in pa.frontiers:
        ide = ident.get(d["pipe"])
        rows.append({**d, "designation": ide.display if ide else None, "identity": ide.key if ide else None,
                     "class": "REAL" if d["reason"] in REAL else "LOSSY" if d["reason"] in LOSSY else "OPEN"})
    return {"page": pa.page.info.index, "reasons": REASONS, "classes": {"REAL": list(REAL), "LOSSY": list(LOSSY), "OPEN": list(OPEN)},
            "summary": sm, "frontiers": rows}


def physical_pipe_dict(m) -> dict[str, Any]:
    p = m.pipe
    return {"physical_pipe_id": p.physical_pipe_id, "page": p.page, "system": p.identity.system, "designation": p.identity.display,
            "identity": p.identity.key, "dn": p.identity.dn, "supporting_anchors": p.anchor_ids, "representation_family": p.family, "section_levels": p.section_levels,
            "geometry": [[[round(x, 2), round(y, 2)] for x, y in pl] for pl in p.points], "source_path_ids": p.source_paths,
            "source_segments": p.source_segments, "graph_nodes": p.nodes,
            "horizontal_pdf_units": round(m.horizontal_pdf_units, 3), "drawn_pdf_units": round(p.length_pt, 3), "raw_pt": round(p.raw_length_pt, 3), "bridged_gap_pt": round(p.bridged_gap_pt, 3),
            "horizontal_m": None if m.horizontal_m is None else round(m.horizontal_m, 3),
            "vertical_m": "UNKNOWN" if m.vertical_m is None else round(m.vertical_m, 3), "vertical_evidence": m.vertical_evidence,
            "total_m": None if m.total_m is None else round(m.total_m, 3), "evidence_state": m.state, "evidence": p.evidence,
            "in_hatched_area_m": None if m.hatched_m is None else round(m.hatched_m, 3),
            "ambiguity_reason": None, "reasons": m.reasons, "needs_review": bool(getattr(p, "needs_review", False)),
            "confidence_tier": tier(p.evidence, bool(getattr(p, "needs_review", False)), getattr(p, "flags", ())),
            "flags": list(getattr(p, "flags", ()) or ()),
            "frontier_reasons": list(p.frontier_reasons), "frontiers": list(getattr(p, "frontiers", []) or [])}


def performance_report(pa, timings: dict) -> dict[str, Any]:
    t = pa.timings
    text_ms = t.get("text_ms", 0.0)
    rep = {"pdf_extraction_ms": round(timings.get("extract_ms", 0.0)), "drawing_profile_ms": round(t.get("profile_ms", 0.0)),
           "glyph_text_reconstruction_ms": round(text_ms), "designation_dn_ms": round(t.get("designation_ms", 0.0)),
           "leader_discovery_and_pipe_attachment_ms": round(t.get("leader_attachment_ms", 0.0)),
           "topology_ms": round(t.get("representation_ms", 0.0) + t.get("topology_ms", 0.0)),
           "physical_pipe_reconstruction_ms": round(t.get("physical_pipes_ms", 0.0)), "measurement_ms": round(t.get("measurement_ms", 0.0)),
           "overlays_ms": round(timings.get("overlays_ms", 0.0)), "artifacts_ms": round(timings.get("artifacts_ms", 0.0)),
           "total_seconds": round(timings.get("total_s", 0.0), 2),
           "counts": {"raw_vector_objects": len(pa.page.paths), "raw_segments": sum(len(p.segs) for p in pa.page.paths),
                      "glyphs": pa.vtext.n_glyphs, "glyph_families": len(pa.vtext.families),
                      "pipe_primitives": sum(len(g.prims) for g in pa.graphs.values()),
                      "graph_nodes": sum(len(g.nodes) for g in pa.graphs.values()), "graph_edges": sum(len(g.prims) for g in pa.graphs.values())}}
    return rep


def source_revision() -> str:
    """Which source read this drawing.

    A result is a reading made by a particular engine, and the engine moves: a takeoff read in April is not the
    takeoff the same drawing gets in September, and a reader looking at an old one deserves to know that rather
    than to wonder why the numbers differ from a colleague's. In a checkout the question is answered by git; a
    deployed image usually has no checkout, so the build writes the revision into the environment instead.
    """
    for var in ("VVS_SOURCE_REVISION", "RAILWAY_GIT_COMMIT_SHA", "SOURCE_COMMIT", "GIT_COMMIT"):
        rev = (os.environ.get(var) or "").strip()
        if rev:
            return rev
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=os.path.dirname(os.path.abspath(__file__)), stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "unknown"


def analysis_report_md(pa, name, timings, determinism, contamination, files) -> str:
    from ..reconcile import reconcile
    rec = reconcile(pa)
    st = Counter(a.state for a in pa.anchors)
    q = pa.quantities
    L = [f"# Analysis report: {name}", "", "## Status",
         f"- designations: {len(pa.designations)} (with DN {sum(1 for d in pa.designations if d.dn is not None)})",
         f"- actual CAD leaders: {len(pa.leaders)} (from designation blocks: {sum(1 for l in pa.leaders if any(d.block_id == l.block_id for d in pa.designations))})",
         f"- pipe attachments: verified {st.get('VERIFIED_PIPE_ATTACHMENT', 0)}, ambiguous {st.get('AMBIGUOUS_PIPE_ATTACHMENT', 0)}, none {st.get('NO_PIPE_ATTACHMENT', 0)}",
         f"- physical pipes: {len(pa.measures)}",
         f"- scale: {pa.scale.state} ({pa.scale.reason})",
         f"- reconciliation: {rec['state']} (raw {rec['raw_relevant_pipe_geometry_pt']} pt = confirmed {rec['confirmed_pt']} + ambiguous {rec['ambiguous_pt']} + unowned {rec['unowned_pt']})",
         f"- determinism: {determinism['state'] if determinism else 'not run'}",
         f"- contamination: {contamination['state'] if contamination else 'not run'}",
         f"- runtime: {timings.get('total_s', 0):.1f} s", "",
         "## Quantities (confirmed only; ambiguous reported separately)", "| Beteckning | DN | Antal | Horisontellt m | Vertikalt m | Totalt m | Tvetydigt m | Status |", "|---|---|---|---|---|---|---|---|"]
    for r in q:
        L.append(f"| {r['designation']} | {r['dn'] if r['dn'] is not None else '?'} | {r['physical_pipe_count']} | {r['confirmed_horizontal_m']:.2f} | {r['vertical_m'] if r['vertical_m']=='UNKNOWN' else f'{r[chr(118)+chr(101)+chr(114)+chr(116)+chr(105)+chr(99)+chr(97)+chr(108)+chr(95)+chr(109)]:.2f}'} | {r['confirmed_total_m']:.2f} | {r['ambiguous_m']:.2f} | {r['state']} |")
    L += ["", f"Totals: confirmed horizontal {sum(r['confirmed_horizontal_m'] for r in q):.2f} m, ambiguous {sum(r['ambiguous_m'] for r in q):.2f} m, unowned pipe geometry {rec['unowned_pt'] * (pa.scale.meters_per_pt or 0):.2f} m", "",
          "## Unresolved", ] + [f"- {k}: {v}" for k, v in Counter(i['kind'] for i in unresolved_issues(pa)).items()]
    L += ["", "## Artifacts"] + [f"- {fn}" for fn in sorted(files)]
    return "\n".join(L) + "\n"
