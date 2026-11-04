"""The pipe assignment asked of Google's Gemini, so it can be measured against the other models on the same sheets.

The question is the one AssignmentTransport builds - the same instructions, sheet overview, questions, detail crops
and answer schema - only sent through the Gemini API with a JSON-schema answer. Which Gemini model is asked is the
operator's choice (VVS_GEMINI_MODEL); by default Google's alias for its latest Pro model.
"""
import base64
import json
import os

from .claude_model import _schema
from .source_model import AssignmentTransport

GEMINI_MODEL = os.environ.get('VVS_GEMINI_MODEL', 'gemini-pro-latest')


def gemini_key():
    return (os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY') or '').strip() or None


def configured():
    return bool(gemini_key())


def _parts(items):
    """OpenAI input parts as Gemini parts: text stays text, a PNG data URL becomes inline image bytes."""
    from google.genai import types
    if isinstance(items, str):
        return [types.Part.from_text(text=items)]
    out = []
    for item in items:
        if item.get('type') == 'input_text':
            out.append(types.Part.from_text(text=item['text']))
        elif item.get('type') == 'input_image':
            head, data = item['image_url'].split(',', 1)
            media = head[len('data:'):].split(';', 1)[0]
            out.append(types.Part.from_bytes(data=base64.b64decode(data), mime_type=media))
    return out


class GeminiTransport(AssignmentTransport):
    def _send(self, system, overview, content, schema=None, key='decisions'):
        from vvs_engine.source_rules.pipestudio.final_bind import SCHEMA
        from . import api_budget
        api_budget.check(self.model)
        schema = schema or SCHEMA
        from google.genai import types
        parts = _parts(overview) + _parts(content)
        config = types.GenerateContentConfig(system_instruction=system, response_mime_type='application/json',
                                             response_json_schema=_schema(schema), max_output_tokens=16000)
        # the request cache compares plain data: the parts as the text and image digests they were built from
        request = {'model': self.model, 'system': system, 'overview': overview, 'content': content, 'schema': schema}

        def produce():
            response = self.client.models.generate_content(
                model=self.model, contents=[types.Content(role='user', parts=parts)], config=config)
            if not isinstance(json.loads(response.text or '{}').get(key), list):
                raise ValueError('Invalid assignment response')
            return response
        try:
            response, reused = self.request_cache.run(request, produce)
        except (ValueError, RuntimeError):
            raise
        except Exception as exc:
            raise RuntimeError(f'Gemini request failed ({type(exc).__name__})') from exc
        u = response.usage_metadata
        cached = 0 if reused else (getattr(u, 'cached_content_token_count', 0) or 0)
        record = {'model': getattr(response, 'model_version', None) or self.model,
                  'response_id': getattr(response, 'response_id', None),
                  'tokens_in': 0 if reused else (getattr(u, 'prompt_token_count', 0) or 0),
                  'tokens_out': 0 if reused else ((getattr(u, 'candidates_token_count', 0) or 0)
                                                  + (getattr(u, 'thoughts_token_count', 0) or 0)),
                  'cached_tokens': cached, 'request_reused': reused}
        if not reused:
            record['kr'] = api_budget.charge(self.model, record['tokens_in'], record['tokens_out'], cached, 0,
                                             'tilldelning')
        return json.loads(response.text)[key], record


def transport(model=None):
    key = gemini_key()
    if not key:
        return None
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=180_000))
    return GeminiTransport(client, model or GEMINI_MODEL)
