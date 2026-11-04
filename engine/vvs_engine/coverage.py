"""Läsningens giltighet: åtta mått på hur mycket av bladet läsningen nådde, och ett omdöme.

Konserveringen (reconcile.py) säger att ingen meter dubbelräknas och att RAW = CONFIRMED + AMBIGUOUS + UNOWNED.
Det är nödvändigt och räcker inte: en läsning som accepterade ingen rörgeometri alls konserverar perfekt.
Giltigheten är den andra frågan - nådde läsningen bladet? - och den ställs i åtta mått som var och en har en
tydlig riktning, och ett omdöme som är strängare ju mer läsningen missat:

  VALID      läsningen nådde bladet: namnen fick meter, bläcket fick ägare, rören slutar med skäl
  DEGRADED   läsningen är giltig men glest: en väsentlig del av det bladet skriver fick inga meter
  INVALID    något som aldrig får hända hände: konserveringen bröts, ett rör slutar tyst, ingen skala,
             eller bladet namnger rör och läsningen mätte inget

Måtten hämtas ur det läsningen redan vet; inget här läser referensen, och inget här flyttar en meter.
"""
from __future__ import annotations

from typing import Any

MEASURES = (
    "DESIGNATIONS_READ",             # antal beteckningar bladet skriver och läsningen läste
    "DESIGNATIONS_WITH_DN_SHARE",    # andel av dem med en dimension
    "ATTACHMENT_VERIFIED_SHARE",     # andel etiketter vars hänvisning nådde ett rör
    "NAMES_WITH_METRES_SHARE",       # andel rörnamn på bladet som fick meter
    "INK_CONFIRMED_SHARE",           # andel av rörpennornas bläck som ägs
    "INK_AMBIGUOUS_SHARE",           # andel som lämnats öppet
    "INK_UNOWNED_SHARE",             # andel ingen etikett nådde
    "FRONTIER_LOSSY_SHARE",          # andel av rörens kanter där meter sannolikt tappas
)

# under de här börjar en läsning vara gles snarare än giltig
DEGRADED_NAMES_WITH_METRES = 0.5
DEGRADED_INK_CONFIRMED = 0.3
DEGRADED_LOSSY_FRONTIERS = 0.35


def coverage_validity(cov: dict[str, Any], anchors: list, reconciliation: dict | None, scale_state: str | None,
                      n_pipes: int) -> dict[str, Any]:
    """Åtta mått och ett omdöme, ur läsningens täckning (pipeline.reading_coverage), ankarna, konserveringen,
    skalans tillstånd och antalet fysiska rör."""
    labels = len(anchors)
    verified = sum(1 for a in anchors if getattr(a, "state", "") == "VERIFIED_PIPE_ATTACHMENT")
    names = cov.get("pipe_names") or 0
    got = cov.get("pipe_names_with_metres") or 0
    # Andelarna räknas på bläcket, inte på metrarna: ett blad utan fastställd skala har inga meter alls, och
    # då blev varje andel None fast den var fullt räknelig. Punkterna finns oavsett vad skalan säger.
    drawn = float(cov.get("drawn_pt") if cov.get("drawn_pt") is not None else (cov.get("drawn_m") or 0.0))
    conf = float(cov.get("confirmed_pt") if cov.get("confirmed_pt") is not None else (cov.get("confirmed_m") or 0.0))
    amb = float(cov.get("ambiguous_pt") if cov.get("ambiguous_pt") is not None else (cov.get("ambiguous_m") or 0.0))
    un = float(cov.get("unowned_pt") if cov.get("unowned_pt") is not None else (cov.get("unowned_m") or 0.0))
    fr = cov.get("frontiers") or {}
    # every edge of every measuring section, the joints to the same pipe's next section included - the share
    # DEGRADED_LOSSY_FRONTIERS was set against, from before the joints were told apart from the pipes' real ends
    n_fr = (fr.get("frontiers") or 0) + (fr.get("section_joints") or 0)
    lossy = fr.get("lossy_boundaries") or 0
    with_dn = cov.get("designations_with_dn")
    n_des = cov.get("designations_read")
    measures = {
        "DESIGNATIONS_READ": n_des if n_des is not None else names,
        "DESIGNATIONS_WITH_DN_SHARE": (round(with_dn / n_des, 3) if n_des else None) if with_dn is not None else None,
        "ATTACHMENT_VERIFIED_SHARE": round(verified / labels, 3) if labels else None,
        "NAMES_WITH_METRES_SHARE": round(got / names, 3) if names else None,
        "INK_CONFIRMED_SHARE": round(conf / drawn, 3) if drawn else None,
        "INK_AMBIGUOUS_SHARE": round(amb / drawn, 3) if drawn else None,
        "INK_UNOWNED_SHARE": round(un / drawn, 3) if drawn else None,
        "FRONTIER_LOSSY_SHARE": round(lossy / n_fr, 3) if n_fr else None,
    }
    reasons: list[str] = []
    verdict = "VALID"
    if reconciliation is not None and reconciliation.get("state") != "VALID":
        verdict = "INVALID"; reasons.append("GEOMETRY_CONSERVATION_BROKEN")
    if fr and fr.get("silent_pipes"):
        verdict = "INVALID"; reasons.append(f"SILENT_PIPES:{len(fr['silent_pipes'])}")
    if cov.get("scale_reason") == "section_not_measured":
        # A section shows the plans' pipes from the side. It is read as a schema is: its designations and
        # components counted, its pipes measured on the plans, so nothing is missing from it.
        measures["NAMES_WITH_METRES_SHARE"] = None
        reasons.append("SECTION_NOT_MEASURED")
        if verdict == "VALID":
            verdict = "SECTION"
    elif cov.get("scale_reason") == "schematic_not_to_scale":
        # A flow or principle diagram is drawn without a scale on purpose: its lines say what connects to what,
        # not how long anything is. Nothing is missing from it - its pipes are measured on the plans - so it is
        # neither a sheet without a scale nor one where nothing was measured, and how many of its pipe names got
        # metres is no question to ask of it. Its designations and components are read and counted.
        measures["NAMES_WITH_METRES_SHARE"] = None
        reasons.append("SCHEMATIC_NOT_TO_SCALE")
        if verdict == "VALID":
            verdict = "SCHEMATIC"
    else:
        if scale_state in (None, "NONE"):
            verdict = "INVALID"; reasons.append("NO_SCALE")
        if names and got == 0 and n_pipes == 0:
            verdict = "INVALID"; reasons.append("SHEET_NAMES_PIPES_BUT_NOTHING_WAS_MEASURED")
        elif not names and not n_pipes:
            verdict = "INVALID"; reasons.append("NO_READABLE_PIPE_LABELS")
    if verdict == "VALID":
        if measures["NAMES_WITH_METRES_SHARE"] is not None and measures["NAMES_WITH_METRES_SHARE"] < DEGRADED_NAMES_WITH_METRES:
            verdict = "DEGRADED"; reasons.append("MOST_NAMES_WITHOUT_METRES")
        if measures["INK_CONFIRMED_SHARE"] is not None and measures["INK_CONFIRMED_SHARE"] < DEGRADED_INK_CONFIRMED and drawn > 0:
            verdict = "DEGRADED"; reasons.append("MOST_PIPE_INK_UNOWNED")
        if measures["FRONTIER_LOSSY_SHARE"] is not None and measures["FRONTIER_LOSSY_SHARE"] > DEGRADED_LOSSY_FRONTIERS:
            verdict = "DEGRADED"; reasons.append("MANY_LOSSY_FRONTIERS")
        if scale_state in ("CONFLICT", "SCALE_UNSETTLED"):
            verdict = "DEGRADED"; reasons.append("SCALE_UNSETTLED")
    return {"verdict": verdict, "reasons": reasons, "measures": measures,
            "thresholds": {"names_with_metres": DEGRADED_NAMES_WITH_METRES, "ink_confirmed": DEGRADED_INK_CONFIRMED,
                           "lossy_frontiers": DEGRADED_LOSSY_FRONTIERS},
            "geometry_conservation": (reconciliation or {}).get("state"),
            "accuracy_verified": False,
            "note": "konservering säger att inget dubbelräknas; giltighet säger om läsningen nådde bladet - två frågor"}


def completion_checks(quality, quantities=(), source_assignment=None, review=None, from_image: bool = False):
    """Completion of checks is independent of how much pipe has an assigned name.

    from_image: the sheet was read from pixels. Everything on it is to be reviewed, and the reading says so."""
    from copy import deepcopy
    result = deepcopy(quality or {'verdict': 'DEGRADED', 'reasons': [], 'measures': {}, 'accuracy_verified': False})
    reasons = result.setdefault('reasons', [])
    checks = []
    if any(float(row.get('review_m') or 0) > 0 for row in quantities):
        checks.append('TENTATIVE_QUANTITIES')
    model = (source_assignment or {}).get('model') or {}
    assignments = (model.get('result') or {}).get('assignments', [])
    if any(a.get('status') == 'unresolved' and a.get('reason') in
           ('unanswered', 'invalid_candidate', 'duplicate_decision') for a in assignments):
        checks.append('MODEL_REVIEW_INCOMPLETE')
    findings = review.get('findings', []) if isinstance(review, dict) else []
    if any(f.get('code') in ('ocr_partial', 'ocr_failed', 'ocr_unavailable') for f in findings):
        checks.append('OCR_REVIEW_INCOMPLETE')
    if from_image:
        checks.append('READ_FROM_IMAGE')
    for reason in checks:
        if reason not in reasons:
            reasons.append(reason)
    # a schema stays a schema: what the checks say is listed, but no metres hang on it
    if checks and result.get('verdict') not in ('INVALID', 'SCHEMATIC', 'SECTION'):
        result['verdict'] = 'DEGRADED'
    return result
