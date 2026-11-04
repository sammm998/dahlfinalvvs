"""Explicit PipeStudio model assignment transport; no VVS5 settlement rules."""
import json
import os
import threading
from pathlib import Path


def connection_settings():
    key=os.environ.get('OPENAI_API_KEY','').strip()
    model=os.environ.get('OPENAI_MODEL','gpt-6-astra')
    if key:return key,model
    filename=os.environ.get('VVS_OPENAI_CONFIG_FILE')
    if not filename:return None,model
    try:
        path=Path(filename)
        if path.stat().st_mode & 0o077:return None,model
        saved=json.loads(path.read_text())
        return str(saved.get('api_key','')).strip() or None, str(saved.get('model') or model)
    except (OSError, ValueError, TypeError):
        return None,model


def configured():
    return bool(connection_settings()[0])


class AssignmentTransport:
    def __init__(self, client, model, style=None, page=None, request_cache=None, places=None, shown=None):
        from .model_request_cache import ModelRequestCache
        # {label id: [(x, y)]}: where each label and its leader are, so the detail crops show them too
        self.places = places or {}
        # {page: {cell}}: the parts of each sheet the model has been shown up close, shared by every copy of the
        # transport, so the sweep never pays to show the same part twice
        self.shown = shown if shown is not None else {}
        self.request_cache = request_cache if request_cache is not None else ModelRequestCache()
        self.client = client
        self.model = model
        self.usage = []
        self.candidate_aliases = []
        self.lock = threading.Lock()
        self.style = style or {"rules": []}
        self.page = page

    def for_style(self, style):
        return type(self)(self.client, self.model, style, self.page, self.request_cache, self.places, self.shown)

    def for_page(self, page):
        return type(self)(self.client, self.model, self.style, (page.source_path, page.info.index), self.request_cache,
                          self.places, self.shown)

    def with_places(self, places):
        return type(self)(self.client, self.model, self.style, self.page, self.request_cache, places, self.shown)

    @property
    def cell(self):
        from .drawing_evidence import CELL
        return CELL

    def _remember(self, images):
        with self.lock:
            seen = self.shown.setdefault(tuple(self.page or ()), set())
            seen.update(tuple(a['cell']) for a in images if a.get('cell'))

    def sweep(self, places, read, max_tiles):
        """Show the model the parts of the sheet where something is unexplained and that it has not seen up close,
        at most `max_tiles` of them, busiest first; return ([{'text', 'cell'}] it saw there and the reading did not
        read, how many cells were shown). Nothing is shown, and nothing paid, when every such part was seen."""
        from vvs_engine.source_rules.completeness_check import SWEEP_SCHEMA, SWEEP_SYSTEM
        from .drawing_evidence import CELL, DETAIL_TILES, render_cells, tally
        if not (self.page and self.page[0]) or max_tiles <= 0:
            return [], 0
        with self.lock:
            seen = set(self.shown.get(tuple(self.page), ()))
        todo = [c for c, _ in sorted(tally([{'points': places}]).items(), key=lambda v: (-v[1], v[0]))
                if c not in seen][:max_tiles]
        found = []
        for i in range(0, len(todo), DETAIL_TILES):
            visual, images = render_cells(*self.page, todo[i:i + DETAIL_TILES])
            self._remember(images)
            overview, details = visual[:2], visual[2:]
            tiles = [a for a in images if a.get('cell')]
            listing = [{'tile': k, 'pdf_rect': a['rect'],
                        'labels_already_read': sorted({t for t, r in read if t and r
                                                       and a['rect'][0] <= (r[0] + r[2]) / 2 <= a['rect'][2]
                                                       and a['rect'][1] <= (r[1] + r[3]) / 2 <= a['rect'][3]})}
                       for k, a in enumerate(tiles)]
            content = [{"type": "input_text", "text": json.dumps({'tiles': listing}, ensure_ascii=False)}] + details
            answer, record = self._send(SWEEP_SYSTEM, overview, content, schema=SWEEP_SCHEMA, key='seen')
            with self.lock:
                self.usage.append(dict(record, drawing_images=images, purpose='sheet_sweep', tiles=len(tiles)))
            for item in answer if isinstance(answer, list) else []:
                k = item.get('tile') if isinstance(item, dict) else None
                if isinstance(k, int) and 0 <= k < len(tiles) and str(item.get('text') or '').strip():
                    found.append({'text': str(item['text']).strip()[:60], 'cell': list(tiles[k]['cell'])})
        return found, len(todo)

    def _looked_at(self, question):
        """Every place a question is about: its pipe's points, and each candidate's label and leader ends."""
        from .drawing_evidence import finite
        pts = [p for p in question.get('points', []) if finite(p)]
        for c in question.get('candidates', []):
            pts.extend(p for p in self.places.get(c.get('label'), ()) if finite(p))
        return {'points': pts}

    def _zoom_groups(self, questions):
        """The questions split so that every place each is about lies in one of the request's detail crops.

        A request shows the model the whole sheet and at most DETAIL_TILES zoomed crops. Questions spread over more
        of the sheet than that were shown only as the overview, where a 2 mm label is a smudge; here they go in
        consecutive requests instead (neighbours stay together), each sharing the cached instructions and overview.
        A question that needs more crops than one request holds is asked alone, its busiest places zoomed."""
        from .drawing_evidence import DETAIL_TILES, cells
        groups, current, seen = [], [], set()
        for q in questions:
            mine = cells([self._looked_at(q)])
            if current and len(seen | mine) > DETAIL_TILES:
                groups.append(current)
                current, seen = [], set()
            current.append(q)
            seen |= mine
        if current:
            groups.append(current)
        return groups

    def _payload(self, questions):
        """What every model is asked: the instructions, the sheet overview, and the questions with their crops."""
        from vvs_engine.source_rules.pipestudio.final_bind import SYSTEM
        from vvs_engine.source_rules.pipestudio.assignment_payload import FORMAT, pack, serialize
        from vvs_engine.source_rules.model_payload import FORMAT as ALIAS_FORMAT, group_equivalent_candidates
        grouped, aliases = group_equivalent_candidates(questions)
        from vvs_engine.source_rules.swedish import label_facts
        for question in grouped:
            for candidate in question.get('candidates', []):
                candidate['swedish_interpretation'] = label_facts({'designations': [candidate.get('designation', {})]})
        content = serialize(pack(grouped))
        images = []
        overview = []
        if self.page and self.page[0] and questions:
            from .drawing_evidence import visual_evidence
            visual, images = visual_evidence(*self.page, [self._looked_at(q) for q in questions])
            self._remember(images)
            # The sheet overview is the same in every request about this page, so it goes first, right after the
            # instructions: the unchanging start of the request is what the provider caches and bills at a fraction.
            # It is sent as a message of its own: the cache matches whole messages, not the start of one.
            overview, details = visual[:2], visual[2:]
            content = [{"type": "input_text", "text": content}] + details
        system = (SYSTEM + '\n' + FORMAT + '\n' + ALIAS_FORMAT + '\nSTYLE CONVENTIONS:\n' + serialize(self.style.get('rules', []))
                  + '\nMEASURED DRAWING FEATURES (observations, not ownership rules):\n' + serialize(self.style.get('observed_features', {})))
        return system, overview, content, images, aliases

    def _cache_key(self):
        # one cache key per sheet: the requests about one page share their opening and are routed to the same cache
        if self.page and self.page[0]:
            import hashlib
            return "fc-bind-" + hashlib.sha1(f"{self.page[0]}#{self.page[1]}".encode()).hexdigest()[:20]
        return None

    def review_flags(self, flags):
        """The consistency flags shown to the model with the places they are at; returns its verdicts."""
        from vvs_engine.source_rules.consistency import REVIEW_SYSTEM, REVIEW_SCHEMA
        numbered = [dict(f, id=i) for i, f in enumerate(flags)]
        overview, content = [], json.dumps({'flags': numbered}, ensure_ascii=False)
        images = []
        if self.page and self.page[0]:
            from .drawing_evidence import visual_evidence
            places = [{'points': [f['at']]} for f in numbered if f.get('at')]
            visual, images = visual_evidence(*self.page, places)
            self._remember(images)
            overview, details = visual[:2], visual[2:]
            content = [{"type": "input_text", "text": content}] + details
        verdicts, record = self._send(REVIEW_SYSTEM, overview, content, schema=REVIEW_SCHEMA, key='verdicts')
        with self.lock:
            self.usage.append(dict(record, drawing_images=images, purpose='consistency_review'))
        return verdicts

    def _send(self, system, overview, content, schema=None, key='decisions'):
        """One request to OpenAI; returns (the answer's `key` list, usage record)."""
        from vvs_engine.source_rules.pipestudio.final_bind import SCHEMA
        from . import api_budget
        api_budget.check(self.model)          # the service's ceiling on what language models may cost
        schema = schema or SCHEMA
        cache_key = self._cache_key()
        request = dict(
            model=self.model, store=False, max_output_tokens=12000,
            **({"prompt_cache_key": cache_key} if cache_key else {}),
            reasoning={'effort': os.environ.get('STUDIO_ASTRA_EFFORT', 'medium')},
            input=[{'role': 'system', 'content': system},
                   *([{'role': 'user', 'content': overview}] if overview else []),
                   {'role': 'user', 'content': content}],
            text={'format': {'type': 'json_schema', 'name': 'pipe_assignments' if key == 'decisions' else key,
                             'strict': True, 'schema': schema}})
        def produce():
            response = self.client.responses.create(**request)
            if response.status != 'completed':
                raise RuntimeError('Model assignment did not complete')
            if not isinstance(json.loads(response.output_text).get(key), list):
                raise ValueError('Invalid assignment response')
            return response
        response, reused = self.request_cache.run(request, produce)
        u = response.usage
        record = {'model': response.model, 'response_id': response.id,
                  'tokens_in': 0 if reused else u.input_tokens if u else None,
                  'tokens_out': 0 if reused else u.output_tokens if u else None,
                  'cached_tokens': 0 if reused else getattr(getattr(u, 'input_tokens_details', None), 'cached_tokens', 0),
                  'request_reused': reused}
        if not reused:
            record['kr'] = api_budget.charge(self.model, record['tokens_in'] or 0, record['tokens_out'] or 0,
                                             record['cached_tokens'] or 0, 0, 'tilldelning')
        if response.status != 'completed':
            raise RuntimeError('Model assignment did not complete')
        return json.loads(response.output_text)[key], record

    def __call__(self, questions):
        decisions = []
        groups = (self._zoom_groups(questions) if self.page and self.page[0] else None) or [questions]
        for group in groups:
            system, overview, content, images, aliases = self._payload(group)
            answered, record = self._send(system, overview, content)
            with self.lock:
                self.candidate_aliases.extend(aliases)
                self.usage.append(dict(record, drawing_images=images, questions=len(group)))
            if not isinstance(answered, list):
                raise ValueError('Invalid assignment response')
            decisions.extend(answered)
        return decisions


def transport(model=None):
    key, configured_model = connection_settings()
    if not key:
        return None
    model = model or configured_model
    from openai import OpenAI
    # A request that has not answered in a minute is split and asked again in smaller pieces by the assignment
    # (engine source_rules/dual.py), which is faster than waiting on it or letting the client repeat it whole.
    return AssignmentTransport(OpenAI(api_key=key, timeout=60, max_retries=0), model)
