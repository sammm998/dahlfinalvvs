"""The pipe assignment asked of Claude instead of OpenAI's model, so the two can be measured on the same sheets.

The question is the one AssignmentTransport builds - the same instructions, the same sheet overview, the same
questions and detail crops, the same answer schema - only sent through Anthropic's Messages API. The instructions and
the overview are marked for prompt caching: every request about one page starts with them, and after the first they
are read from the cache at a tenth of the price.
"""
import copy
import json
import os

from .source_model import AssignmentTransport

CLAUDE_MODEL = 'claude-opus-5-5'
# USD per million tokens (Anthropic first-party API): input, output, cache read, cache write (5 minutes)
PRICES = {'claude-opus-5-5': (4.00, 20.00, 0.20, 5.00),
          # Anthropics mest kapabla modell: tänker alltid (ingen thinking-parameter skickas), samma output_config
          'claude-fable-5-2': (8.00, 40.00, 0.20, 10.00)}


def anthropic_key():
    return os.environ.get('ANTHROPIC_API_KEY', '').strip() or None


def configured():
    return bool(anthropic_key())


def _schema(schema):
    """The answer schema in the form structured outputs take: a list of types becomes anyOf."""
    def walk(node):
        if isinstance(node, dict):
            node = {k: walk(v) for k, v in node.items()}
            if isinstance(node.get('type'), list):
                types = node.pop('type')
                node = {'anyOf': [{'type': t} for t in types], **node}
            return node
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node
    return walk(copy.deepcopy(schema))


def _blocks(items):
    """OpenAI input parts as Anthropic content blocks: text stays text, a PNG data URL becomes a base64 image."""
    if isinstance(items, str):
        return [{'type': 'text', 'text': items}]
    out = []
    for item in items:
        if item.get('type') == 'input_text':
            out.append({'type': 'text', 'text': item['text']})
        elif item.get('type') == 'input_image':
            head, data = item['image_url'].split(',', 1)
            media = head[len('data:'):].split(';', 1)[0]
            out.append({'type': 'image', 'source': {'type': 'base64', 'media_type': media, 'data': data}})
    return out


def usd(model, tokens_in, tokens_out, cache_read, cache_write):
    price = PRICES.get(model)
    if price is None:
        return None
    fresh = max(0, tokens_in - cache_read - cache_write)
    return round((fresh * price[0] + tokens_out * price[1] + cache_read * price[2] + cache_write * price[3]) / 1e6, 4)


class ClaudeTransport(AssignmentTransport):
    def _send(self, system, overview, content, schema=None, key='decisions'):
        from vvs_engine.source_rules.pipestudio.final_bind import SCHEMA
        from . import api_budget
        api_budget.check(self.model)
        schema = schema or SCHEMA
        import anthropic
        opening = _blocks(overview)
        if opening:
            opening[-1] = dict(opening[-1], cache_control={'type': 'ephemeral'})
        request = dict(
            model=self.model, max_tokens=16000,
            system=[{'type': 'text', 'text': system, 'cache_control': {'type': 'ephemeral'}}],
            messages=[{'role': 'user', 'content': opening + _blocks(content)}],
            output_config={'effort': os.environ.get('VVS_CLAUDE_EFFORT', 'medium'),
                           'format': {'type': 'json_schema', 'schema': _schema(schema)}},
            # a request a safety classifier declines is answered by Anthropic's recommended fallback model instead
            betas=['server-side-fallback-2026-07-01'], fallbacks='default')
        def produce():
            response = self.client.beta.messages.create(**request)
            if response.stop_reason == 'refusal':
                raise RuntimeError('Claude declined the assignment request')
            if response.stop_reason == 'max_tokens':
                raise RuntimeError('Claude ran out of output tokens')
            text = next(b.text for b in response.content if b.type == 'text')
            if not isinstance(json.loads(text).get(key), list):
                raise ValueError('Invalid assignment response')
            return response
        try:
            response, reused = self.request_cache.run(request, produce)
        except anthropic.APIStatusError as exc:
            raise RuntimeError(f'Claude request failed ({exc.status_code})') from exc
        u = response.usage
        read = 0 if reused else (u.cache_read_input_tokens or 0)
        written = 0 if reused else (u.cache_creation_input_tokens or 0)
        tokens_in = 0 if reused else u.input_tokens + read + written
        tokens_out = 0 if reused else u.output_tokens
        record = {'model': response.model, 'response_id': response.id, 'tokens_in': tokens_in,
                  'tokens_out': tokens_out, 'cached_tokens': read, 'cache_write_tokens': written,
                  'usd': usd(self.model, tokens_in, tokens_out, read, written), 'request_reused': reused}
        if not reused:
            record['kr'] = api_budget.charge(self.model, tokens_in, tokens_out, read, written, 'tilldelning')
        text = next(b.text for b in response.content if b.type == 'text')
        return json.loads(text)[key], record


def transport(model=CLAUDE_MODEL):
    key = anthropic_key()
    if not key:
        return None
    import anthropic
    # Claude thinks before it answers; a batch is given three minutes before the assignment splits it and asks again
    return ClaudeTransport(anthropic.Anthropic(api_key=key, timeout=180, max_retries=0), model)
