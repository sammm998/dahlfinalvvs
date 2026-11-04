"""Run PipeStudio's original detection stages on annotation-free drawing ink.

Original source modules stay byte-identical. No expert boxes, feedback or
reference quantities are inputs. The caller owns assignment and measurement.
"""
from dataclasses import asdict
import hashlib
import json
import re
import os
from pathlib import Path
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / 'reference_sources' / 'pipestudio-main'


def _pdf_digest(path):
    with open(path, 'rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load_runtime():
    source = str(SOURCE)
    if source not in sys.path:
        sys.path.insert(0, source)
    os.environ.setdefault('AI_MODEL_PATH', str(ROOT / 'models/pipestudio-labels.onnx'))
    # Two OCR processes unless the operator says otherwise (PIPE_OCR_WORKERS). The core count is not a safe guide:
    # a container sees every core of its host but not its own memory limit, and eight tesseract processes at once
    # took a Railway service past that limit - it was restarted mid-analysis and every page answered 502.
    os.environ.setdefault('PIPE_OCR_WORKERS', '2')
    os.environ.setdefault('OMP_THREAD_LIMIT', '1')
    os.environ.setdefault('PIPE_STUDIO_DATA', str(ROOT / '.local/native-studio'))
    import pytesseract
    local = ROOT / '.local/tesseract/bin/tesseract'
    if local.exists():
        pytesseract.pytesseract.tesseract_cmd = str(local)
    from vectorascore import extract, profile, detect, labels, style
    from studio.engine import vector_stages
    return extract, profile, detect, labels, style, vector_stages


MIN_LANDINGS = 10        # leader landings on a pen before the sheet's own word can outvote the chosen pipe pen
LANDING_MARGIN = 5       # ...that many times the landings on the chosen pen
LENGTH_MARGIN = 3        # ...and that many times its landed-on length (PipeStudio's own flip rule, bucket.calibrate)
LIBRARY_MARGIN = 1.5     # both margins when the chosen pen is another office's stored style rather than this sheet's
                         # own width rule: a value measured on a different sheet yields to this sheet's leaders sooner
                         # (V-50-1-666340-0113 with every pen black: 40 landings on 1.44 pt against 25 on the stored
                         # style's 0.72 pt, now the building's black outline)


def landed_policy(ex, B, extra_pipe_widths=()):
    """The pens this sheet's own leaders point at, when they contradict the pipe pen the calibration chose.

    The calibration may take a known style's starting values for the pipe pen. A sheet from another office that
    happens to measure like that style then reads its grey building outline as pipes and its real pipes as nothing
    (V-50-1-666340-0113: the 'Arildsson' starting value 0.72 pt, while 32 of the sheet's leaders land on its 1.44 pt
    black pen and 3 on 0.72). Where the leaders say otherwise by PipeStudio's own margin, the pen they land on is
    the pipe pen, their own pen is the leader pen, grey ink is the building, and the other black pens keep their
    ordinary reading. Returned as a stroke policy for PipeStudio's style mechanism; None when nothing contradicts.
    """
    from studio.style_vision import inventory
    C = B.get('calibration') or {}
    land = C.get('landings') or {}
    votes = land.get('votes') or {}
    chosen = {round(float(w), 2) for w in C.get('pipe_widths') or []}
    def width(key):
        return round(float(key.split('|')[0]), 2)
    black = {k: v for k, v in votes.items() if k.endswith('|black')}
    if not black:
        return None
    best_key = max(black, key=lambda k: (black[k]['landings'], black[k]['length']))
    best = black[best_key]
    if width(best_key) in chosen:
        return None
    on_chosen = sum(v['landings'] for k, v in black.items() if width(k) in chosen)
    length_chosen = sum(v['length'] for k, v in black.items() if width(k) in chosen)
    stored = (C.get('family_method') or '').startswith('library starting values')
    landing_margin, length_margin = (LIBRARY_MARGIN, LIBRARY_MARGIN) if stored else (LANDING_MARGIN, LENGTH_MARGIN)
    if not (best['landings'] >= MIN_LANDINGS and best['landings'] >= landing_margin * max(on_chosen, 1)
            and best['length'] >= length_margin * max(length_chosen, 1.0)):
        return None
    leaders = land.get('leader_families') or {}
    leader_w = width(max(leaders, key=leaders.get)) if leaders else None
    unit = C.get('u_paper') or 1.0
    pipe_w = width(best_key) / unit
    families = []
    for f in inventory(ex, unit):
        k = f['key']
        grey = bool(k['color']) and max(k['color']) - min(k['color']) < .05 and min(k['color']) > .2
        coloured = bool(k['color']) and max(k['color']) - min(k['color']) >= .05
        if (abs(k['width'] - pipe_w) <= .015 or any(abs(k['width'] - w / unit) <= .005 for w in extra_pipe_widths)) \
                and not grey and not coloured:
            role = 'pipe'
        elif leader_w is not None and abs(k['width'] - leader_w / unit) <= .015 and not grey and not coloured:
            role = 'leader'
        elif grey:
            role = 'architecture'
        else:
            role = 'symbol'
        families.append({'key': k, 'role': role})
    if not any(f['role'] == 'pipe' for f in families):
        return None
    return {'policy': {'families': families},
            'report': {'chosen_pipe_widths': sorted(chosen), 'landed_pipe_pen': best_key,
                       'landings': best['landings'], 'landings_on_chosen': on_chosen,
                       'leader_pen': leader_w, 'method': C.get('family_method')}}


def dashed_pens(ex, B):
    """The pens a sheet may draw its leaders in, the measured leader pen first: every black stroke pen thinner than
    the pipe pen. The measured one can be wrong - on V-50-1-666340-0112 the leaders that land on nothing vote for
    0.96 pt, while the leaders to the dashed pipes are drawn in 0.48 pt."""
    C = B.get('calibration') or {}
    chosen = [round(float(w), 3) for w in C.get('pipe_widths') or []]
    pipe = min(chosen or [1e9])
    first = C.get('leader_width')
    widths = sorted({round(p.width, 3) for p in ex.paths if p.kind == 's' and p.duplicate_of is None
                     and (not p.color or max(p.color) <= .25) and 0 < p.width < pipe - .015})
    pens = [round(first, 3)] if first else []
    pens += [w for w in widths if not pens or abs(w - pens[0]) > .015]
    # the pipe pen itself, when only a few leaders chose it: after V-50-1-666340-0112's split-form labels were read,
    # 7 leaders landing on the dashed 0.48 pt pipes made 0.48 pt the pipe pen, and the leaders became pipe ink too
    votes = (C.get('landings') or {}).get('votes') or {}
    landed_on = sum(v['landings'] for k, v in votes.items() if abs(float(k.split('|')[0]) - pipe) <= .015)
    if len(chosen) == 1 and landed_on < MIN_LANDINGS:
        pens.append(pipe)
    return pens


def kept_policy(ex, B, extra_pipe_width, leader_width):
    """The first reading's own pens as a stroke policy, with the dashed strokes filed apart read as pipe ink.

    For a sheet where the leaders contradict nothing - its pipe pen stands - but some pipes are drawn dashed in the
    leader pen (V-50-1-666340-0111: the only pipes on the sheet are KV2-E13-25/SRN, dashed 0.48 pt, and its four
    leaders end on them). Every other family keeps the role most of its ink had in the first reading."""
    from studio.style_vision import inventory
    from vectorascore.geom import path_length
    C = B.get('calibration') or {}
    unit = C.get('u_paper') or 1.0
    buckets = B.get('buckets') or {}
    families = []
    for f in inventory(ex, unit):
        k = f['key']
        black = not k['color'] or max(k['color']) <= .25
        if abs(k['width'] - extra_pipe_width / unit) <= .005 and black:
            role = 'pipe'
        elif leader_width is not None and abs(k['width'] - leader_width / unit) <= .005 and black:
            role = 'leader'      # the pen the leaders to the dashed pipes are drawn in, even if it read as pipe
        else:
            ink = {}
            for p in f['paths']:
                b = buckets.get(str(p.id), buckets.get(p.id))
                ink[b] = ink.get(b, 0.0) + path_length(p.items)
            top = max(ink, key=ink.get) if ink else None
            if top == 'pipe':
                role = 'pipe'
            elif leader_width is not None and abs(k['width'] - leader_width / unit) <= .015 and black:
                role = 'leader'
            elif top in ('architecture', 'unknown'):
                role = top
            else:
                role = 'symbol'
        families.append({'key': k, 'role': role})
    return {'policy': {'families': families},
            'report': {'chosen_pipe_widths': sorted(C.get('pipe_widths') or []), 'dashed_pipe_pen': extra_pipe_width,
                       'leader_pen': leader_width, 'method': C.get('family_method')}}


LOOKS_LIKE_ZERO = re.compile(r"[Oo](?=\d)|(?<=\d)[Oo]")
KNOWN_COVER = 0.6        # the rows read from the vector glyphs must span this share of a label box's height and width


def read_labels_known(labels, clean, det, page_number, known_text):
    """The label boxes read, with tesseract only where the drawing's own vector text did not already say it.

    On a sheet whose lettering is drawn as strokes, the host reading has already built every row of text from the
    glyphs before the native detector runs, and OCR then reads the same lettering again from a raster - several
    passes per box, the slowest step of the whole reading (101 of 230 s on W-50-1-A-0123). A box whose vector rows
    span it and parse to designations that all carry a size is taken from those rows. Anything else - a box the
    rows do not cover, a row without a size, nothing read at all - goes to the OCR exactly as before.
    """
    boxes = det.get('label_boxes', [])
    if not known_text or not boxes:
        return labels.read_labels(clean, det, page_no=page_number)
    import pymupdf
    from pipe_types import stroke_bars
    from vectorascore import vvs
    known, rest = {}, []
    for b in boxes:
        x0, y0, x1, y1 = b['rect']
        rows = [r for r in known_text
                if x0 - 1 <= (r['bbox'][0] + r['bbox'][2]) / 2 <= x1 + 1 and y0 - 1 <= (r['bbox'][1] + r['bbox'][3]) / 2 <= y1 + 1
                and r['text'].strip()]
        # only lettering written left to right: which row of a turned label comes first is the OCR's to say
        if not rows or any(abs(r.get('angle') or 0) > 1 for r in rows):
            rest.append(b)
            continue
        rows.sort(key=lambda r: r['bbox'][1])
        ux0, uy0 = min(r['bbox'][0] for r in rows), min(r['bbox'][1] for r in rows)
        ux1, uy1 = max(r['bbox'][2] for r in rows), max(r['bbox'][3] for r in rows)
        # The box is a little taller than its lettering: the detector frames a label with a margin. What matters
        # is that no row of it can be left unread - that the height the rows leave over could not hold another.
        row_h = min(r['bbox'][3] - r['bbox'][1] for r in rows)
        room = (y1 - y0) - (uy1 - uy0)
        if (ux1 - ux0) < KNOWN_COVER * (x1 - x0) or ((uy1 - uy0) < KNOWN_COVER * (y1 - y0) and room >= row_h):
            rest.append(b)
            continue
        texts = [r['text'].strip() for r in rows]
        # drawn lettering makes O and 0 the same ring: VVCO1 is VVC01 to the eye and another system to the parser.
        # Which one it is, is the OCR's to say.
        if any(LOOKS_LIKE_ZERO.search(t) for t in texts):
            rest.append(b)
            continue
        des, level, unknown = vvs.parse_block(texts)
        des = [vvs.sanitize_dimension(d) for d in des]
        if not des or not all(d.get('dimension') and d.get('system') for d in des) or unknown:
            rest.append(b)
            continue
        known[b['id']] = (b, rows, texts, des, level, unknown)
    out = {r['id']: r for r in (labels.read_labels(clean, dict(det, label_boxes=rest), page_no=page_number) if rest else [])}
    if known:
        with pymupdf.open(clean) as doc:
            page = doc[page_number]
            for bid, (b, rows, texts, des, level, unknown) in known.items():
                trip = [(t, pymupdf.Rect(*r['bbox']), 100.0) for t, r in zip(texts, rows)]
                bars = stroke_bars(page, b['rect'], trip)
                out[bid] = {'id': b['id'], 'rect': b['rect'], 'score': b['score'], 'text': '\n'.join(texts),
                            'src': 'vector_text', 'cls': b.get('cls'), 'in_wall': False,
                            'valid': labels.label_valid(des, b['score']),
                            'usable': any(d.get('dimension') for d in des),
                            'rows': [{'text': t, 'rect': [round(v, 2) for v in r['bbox']], 'conf': 100.0}
                                     for t, r in zip(texts, rows)],
                            'designations': des, 'level': level, 'unknown_rows': unknown, 'stroke_bars': bars,
                            'stroke_notation': {'over': any(x['side'] == 'over' for x in bars),
                                                'under': any(x['side'] == 'under' for x in bars)} if bars else None,
                            'layer_system': None}
    return [out[b['id']] for b in boxes if b['id'] in out]


def detect_page(pdf_path, page_number=0, style=None, progress=None, artifact_dir=None, strict_original=False,
                known_text=None):
    import pymupdf
    from ..pdf.extract import _inventory_annotations, _set_markup_aside
    extract, profile, detect, labels, style_module, vector_stages = load_runtime()
    timings = {}
    def save(name, value):
        if artifact_dir:
            target = Path(artifact_dir) / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('w') as stream:
                json.dump(value, stream, ensure_ascii=False)
    def stage(name, fn):
        if progress: progress('PIPESTUDIO_' + name.upper())
        start = time.monotonic()
        value = fn()
        timings[name] = round(time.monotonic() - start, 3)
        return value
    with tempfile.TemporaryDirectory(prefix='vvs-native-') as tmp:
        clean = str(Path(tmp) / 'original-ink.pdf')
        with pymupdf.open(pdf_path) as doc:
            for page in doc:
                report = _set_markup_aside(page, _inventory_annotations(page), keep=False)
                if report and report.get('partial'):
                    raise ValueError('Cannot isolate original drawing ink for native detection')
            doc.save(clean)
        if strict_original:
            det = stage('detect', lambda: detect.detect(clean, page_number))
        else:
            from .tiled_detection import detect as bounded_detect
            det = stage('detect', lambda: bounded_detect(clean, page_number, progress=progress))
        # Model inference does not need the vector graph. Build it afterwards
        # so its allocations do not overlap the ONNX working set.
        ex = stage('extract', lambda: extract.extract(clean, page_number))
        # the strokes as the PDF holds them: the reading below may split a stroke or file it under a pen of its
        # own, but the measurement matches the reading's pipes to the page by the PDF's own strokes
        original_ex = ex
        boxed = {'split': 0}
        if not strict_original:
            from .boxed_leaders import split, reorder_leaders
            from .pipestudio.vvs import parse_designation
            # the detector's label boxes, and the text spans that write a pipe designation: the boxes built from
            # the text layer come later, and a label found only there has its frame and leader drawn just the same
            label_rects = [b['rect'] for b in det.get('label_boxes', [])]
            # a text span's box is the letters' own: its underline runs a few points past them on either side
            text_rects = [[t.bbox[0] - 3, t.bbox[1] - 2, t.bbox[2] + 3, t.bbox[3] + 2] for t in ex.texts
                          if any(parse_designation(w) for w in t.text.split())]
            ex, boxed = split(ex, label_rects)
            ex, by_text = split(ex, text_rects, underline_only=True)
            boxed = dict(boxed, by_text=by_text.get('split', 0), paths=boxed.get('paths', []) + by_text.get('paths', []))
            label_rects = label_rects + text_rects
            ex, reordered = reorder_leaders(ex, label_rects)
            boxed = dict(boxed, reordered=reordered)
        P = stage('profile', lambda: profile.profile(ex))
        det = labels.text_label_boxes(ex, det, text_height=style_module.text_height(ex)[0])
        L = stage('ocr', lambda: read_labels_known(labels, clean, det, page_number, known_text))
        rotated_repairs = []
        if not strict_original:
            from .rotated_labels import repair
            with pymupdf.open(clean) as text_doc:
                rotated_repairs = repair(text_doc[page_number], L)
        shelves = {'widened': 0}
        recovered, rejoined = {'recovered': 0}, 0
        if not strict_original:
            from .text_labels import recover, rejoin
            L, rejoined = rejoin(L)
            det, L, recovered = recover(clean, page_number, det, L, ex, labels.read_labels,
                                        style_module.text_height(ex)[0])
            from .label_shelves import extend_to_shelves
            det, L, shelves = extend_to_shelves(ex, det, L)
        save('detection-inputs.json', {'extraction': asdict(ex), 'profile': P,
                                     'detection': det, 'labels': L, 'timings': timings})
        # Unknown styles still use the original automatic measurement/calibration.
        if style is None:
            from studio.engine import detect_style
            from studio.styles import get_style
            match = detect_style(ex, P)
            style = get_style(match['style_id']) if match.get('style_id') else {}
        else:
            match = {'status': 'caller_profile', 'style_id': style.get('id')}
        selected = dict(style)
        selected.setdefault('id', 'auto')
        selected.setdefault('version', 1)
        selected.setdefault('calibration', {})
        selected.setdefault('rules', [])
        selected['calibration_mode'] = 'auto'
        unparsed = [l for l in L if not l.get('designations')]
        if not strict_original:
            # Original associate._split_shared_line calls max() on every OCR
            # designation list. Empty lists crash that stage. Preserve such
            # readings in the audit, but do not treat them as pipe labels.
            excluded = {l['id'] for l in unparsed}
            L = [l for l in L if l['id'] not in excluded]
            det = {**det, 'label_boxes': [b for b in det['label_boxes'] if b['id'] not in excluded]}
        renumbered, declared = {}, []
        if not strict_original:
            from .label_ids import renumber, declared_systems
            det, L, renumbered = renumber(det, L)
            L, declared = declared_systems(L)
        read = L
        B, A, L, R = stage('vector_stages', lambda: vector_stages(ex, P, det, read, selected, mode='auto'))
        landed = None if selected.get('stroke_policy') is not None else landed_policy(ex, B)
        dashed = {'pipes': 0}
        if landed is not None and landed['report'].get('leader_pen'):
            pens = [landed['report']['leader_pen']]
        elif landed is None and selected.get('stroke_policy') is None:
            pens = dashed_pens(ex, B)
        else:
            pens = []
        from .dashed_pipes import dashed_paths, leaders_ending_on, file_apart, MIN_LEADERS
        boxes = [b['rect'] for b in det.get('label_boxes', [])]
        for pen in pens:
            # pipes drawn dashed in the leader pen, which the sheet's own leaders point at (dashed_pipes.py)
            ids = dashed_paths(ex, pen)
            hits = leaders_ending_on(ex, ids, boxes, pen)
            if hits > dashed.get('leaders_on_them', -1):
                dashed = {'pipes': len(ids), 'leaders_on_them': hits, 'leader_pen': pen}
            if hits >= MIN_LEADERS:
                ex, apart = file_apart(ex, ids, pen)
                again = landed_policy(ex, B, extra_pipe_widths=(apart,))
                if again is not None:
                    landed = again
                elif landed is None:
                    landed = kept_policy(ex, B, apart, pen)
                dashed['pen'] = apart
                break
        if landed is not None:
            # the matched style was contradicted by the sheet: none of its measures is taken, only the sheet's own
            selected = {'id': 'auto', 'version': 1, 'calibration': {}, 'rules': [], 'calibration_mode': 'auto',
                        'stroke_policy': landed['policy'], 'landed_pens': dict(landed['report'],
                                                                              set_aside_style=selected.get('id'))}
            B, A, L, R = stage('vector_stages_landed', lambda: vector_stages(ex, P, det, read, selected, mode='auto'))
        from .free_end_landings import land_free_ends
        R, rescued = land_free_ends(A, R, L)
        split_from = {}
        for report in (boxed, boxed.get('reordered') or {}):
            for item in (report.get('paths') or []):
                for new_id in (item.get('leader_paths') or []) + (item.get('marks') or []):
                    split_from[new_id] = item['path']
        return {'source_pdf_sha256': _pdf_digest(pdf_path), 'free_end_landings': rescued,
                'page': page_number, 'extraction': asdict(original_ex), 'split_from': split_from, 'profile': P,
                'detection': det, 'bucket': B, 'graph': A, 'labels': L,
                'association': R, 'timings': timings, 'style': selected, 'style_match': match,
                'unparsed_labels': unparsed, 'strict_original': strict_original,
                'rotated_text_repairs': rotated_repairs, 'boxed_leaders': boxed, 'label_shelves': shelves,
                'dashed_pipes': dashed, 'text_labels': dict(recovered, rejoined=rejoined),
                'label_ids_from': renumbered, 'declared_systems': declared,
                'annotations_used': False, 'expert_overrides_used': False}


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pdf'); parser.add_argument('--out', required=True)
    parser.add_argument('--page', type=int, default=0)
    parser.add_argument('--strict-original', action='store_true')
    args = parser.parse_args()
    result = detect_page(args.pdf, args.page, progress=lambda s: print(s, flush=True),
                         artifact_dir=Path(args.out).parent, strict_original=args.strict_original)
    target = Path(args.out); target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False))
    print(json.dumps({'timings': result['timings'], 'labels': len(result['labels']),
                      'stretches': len(result['graph']['stretches'])}), flush=True)


if __name__ == '__main__':
    main()
