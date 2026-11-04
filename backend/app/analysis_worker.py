"""A PDF analysis can be terminated even while a single page is being read."""
from __future__ import annotations

import multiprocessing
import logging
import signal
from pathlib import Path
import time
import traceback


def _cached_detector(output_dir, detect_page, persistent_dir=None, revision=None, cache_context=None):
    """Reuse expensive extraction, but isolate each scale pass's graph edits."""
    import json
    import pickle
    import tempfile
    from pathlib import Path
    # Only files created by this closure are read as pickle, from a private
    # temporary directory. Preserve tuple/int-key types without retaining all
    # pages' graphs in RAM or accepting uploaded pickle artifacts.
    cache = tempfile.TemporaryDirectory(prefix='vvs-detector-cache-')
    detected = {}

    def detector(pdf, page, **options):
        key = (str(Path(pdf).resolve()), page)
        if key not in detected:
            target = Path(output_dir) / 'native-detection' / str(page)
            if persistent_dir and revision:
                from .native_cache import reuse_detection
                result = reuse_detection(persistent_dir, revision, cache_context, detect_page,
                                         pdf, page, target, options)
            else:
                result = detect_page(pdf, page, artifact_dir=target, **options)
            target.mkdir(parents=True, exist_ok=True)
            with (target / 'result.json').open('w') as stream:
                json.dump(result, stream, ensure_ascii=False)
            cached = Path(cache.name) / str(len(detected))
            with cached.open('wb') as stream:
                pickle.dump(result, stream, protocol=pickle.HIGHEST_PROTOCOL)
            detected[key] = cached
            del result
        with detected[key].open('rb') as stream:
            return pickle.load(stream)

    return detector


def _child(connection, args, kwargs, rule_values):
    try:
        # this process asks language models too: through the service's ledger and under its ceiling
        from .api_budget import install_meter
        install_meter()
        label_audit = kwargs.pop('label_audit', False)
        from vvs_engine.cli import analyze_pdf
        from vvs_engine import rules, disciplines
        discipline = kwargs.pop('discipline', None)
        if kwargs.pop('second_reader_enabled', False):
            from tools.readers import panel_transport
            kwargs['second_reader'] = panel_transport()
        # the language model the reading was started with, or none: the sheet's own evidence answers then
        from . import ai_models
        ai_model = kwargs.pop('ai_model', None) or ai_models.default()
        if kwargs.get('source_mode') in ('model', 'compare', 'combined'):
            kwargs['source_ask'] = ai_models.transport(ai_model)
            if ai_model != ai_models.NONE and kwargs['source_ask'] is None:
                raise RuntimeError(f'{ai_models.LABELS.get(ai_model, ai_model)} är inte ansluten på servern.')
        persistent_dir = kwargs.pop('native_cache_dir', None)
        if kwargs.pop('native_detection', False):
            from vvs_engine.source_rules.native_detection import detect_page
            import os
            revision = os.environ.get('RAILWAY_GIT_COMMIT_SHA') or os.environ.get('VVS_BUILD')
            kwargs['source_detector'] = _cached_detector(args[1], detect_page, persistent_dir,
                                                        revision, rule_values)
        kwargs['progress']=lambda *a:connection.send(('progress',a))
        kwargs['film_sink']=lambda *a:connection.send(('film',a))
        with rules.using(rule_values), disciplines.using(discipline):
            result=analyze_pdf(*args,**kwargs)
        # Annotations were removed before inference; this report is never fed back.
        # a sheet the reading turned upright was read from the turned copy, and that copy is what is checked
        import os as _os
        read = _os.path.join(args[1], result['upright_file']) if result.get('upright_file') else args[0]
        from .reference_audit import write_report
        write_report(read, args[1])
        if label_audit:
            import json
            from pathlib import Path
            try:
                from vvs_engine.label_detector import audit
                reports = audit(read, args[1], Path(__file__).resolve().parents[2]/'models/pipestudio-labels.onnx')
                audit_status = {'state':'COMPLETED','pages':len(reports),
                                'unmatched_proposals':sum(r['unmatched_proposals'] for r in reports)}
            except Exception as e:
                audit_status = {'state':'UNAVAILABLE','reason':str(e)}
            (Path(args[1])/'label-audit-status.json').write_text(json.dumps(audit_status))
            result['summary']['label_audit'] = audit_status
        connection.send(('result',result))
    except Exception as e:
        connection.send(('error',{'type':type(e).__name__,'message':str(e),
                                  'traceback':traceback.format_exc(),
                                  'pages':getattr(e,'classifications',[])}))
    finally:
        connection.close()


def _oom_kills():
    """Linux cgroup v2 evidence, unavailable on other hosts or older cgroups."""
    try:
        values = dict(line.split() for line in Path('/sys/fs/cgroup/memory.events').read_text().splitlines())
        return int(values['oom_kill'])
    except (OSError, ValueError, KeyError):
        return None


def _worker_failure(process, oom_before, last_stage):
    # Pipe EOF can arrive before multiprocessing has reaped the process.
    # Joining first avoids reporting exitcode=None for a terminated worker.
    process.join(timeout=2)
    code = process.exitcode
    oom_after = _oom_kills()
    if oom_before is not None and oom_after is not None and oom_after > oom_before:
        reason = 'Serverns minnesgräns nåddes och containern rapporterade ett minnesstopp (OOM).'
    elif code == -signal.SIGKILL:
        reason = 'Analysprocessen stoppades av servern (SIGKILL). Minnesbrist är en möjlig orsak; kontrollera serverloggen.'
    elif code is not None and code < 0:
        try:
            name = signal.Signals(-code).name
        except ValueError:
            name = str(-code)
        reason = f'Analysprocessen kraschade eller avbröts av en signal ({name}).'
    elif code is None:
        reason = 'Kontakten med analysprocessen stängdes innan processen avslutades.'
    else:
        reason = f'Analysprocessen avslutades utan resultat (kod {code}).'
    stage = f' Senaste analyssteg: {last_stage}.' if last_stage else ''
    logging.getLogger(__name__).error('Analysis worker failed: exitcode=%s, stage=%s, oom_before=%s, oom_after=%s',
                                    code, last_stage, oom_before, oom_after)
    return RuntimeError(reason + stage + ' Ingen ofullständig mängd publiceras.')


def analyze_isolated(*args, progress=None, film_sink=None, rule_values=None, **kwargs):
    from vvs_engine.cli import AnalysisTookTooLong
    from vvs_engine.pdf.extract import UnsupportedInputError
    budget=kwargs.get('deadline_s')
    deadline=time.monotonic()+budget if budget is not None else float('inf')
    context=multiprocessing.get_context('spawn')
    receive,send=context.Pipe(duplex=False)
    process=context.Process(target=_child,args=(send,args,kwargs,rule_values or {}),daemon=True)
    oom_before = _oom_kills()
    last_stage = None
    process.start();send.close()
    try:
        while True:
            left=deadline-time.monotonic()
            if left<=0:
                raise AnalysisTookTooLong(f'Analysen avbröts efter tidsgränsen {budget:g} sekunder. Ingen ofullständig mängd publiceras.')
            if receive.poll(min(.25,left)):
                try:
                    kind,payload=receive.recv()
                except EOFError:
                    raise _worker_failure(process, oom_before, last_stage) from None
                if kind=='result':
                    return payload
                if kind=='error':
                    if payload['type']=='UnsupportedInputError':
                        raise UnsupportedInputError(payload['message'],payload['pages'])
                    if payload['type']=='AnalysisTookTooLong':
                        raise AnalysisTookTooLong(payload['message'])
                    raise RuntimeError(payload['type']+': '+payload['message'])
                if kind=='progress':
                    last_stage = str(payload[0]) if payload else last_stage
                    if progress:
                        progress(*payload)
                if kind=='film' and film_sink:
                    film_sink(*payload)
            elif not process.is_alive():
                raise _worker_failure(process, oom_before, last_stage)
    finally:
        receive.close()
        process.join(timeout=.2)
        if process.is_alive():
            process.terminate();process.join(timeout=2)
        if process.is_alive():
            process.kill();process.join(timeout=2)
        process.close()
