"""The pipe assignment asked of Gemini: the same question as the other models, in Google's form, its tokens counted."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))

from app import ai_models
from app.gemini_model import GeminiTransport, _parts


class FakeModels:
    def __init__(self, decisions):
        self.decisions, self.requests = decisions, []

    def generate_content(self, **request):
        self.requests.append(request)
        usage = SimpleNamespace(prompt_token_count=1200, candidates_token_count=150, thoughts_token_count=50,
                                cached_content_token_count=800)
        return SimpleNamespace(text=json.dumps({'decisions': self.decisions}), usage_metadata=usage,
                               model_version='gemini-x-pro', response_id='r1')


def question():
    return {'stretch': 4, 'length': 10.0, 'line_type': 'solid', 'layer': '', 'points': [[0, 0], [10, 0]],
            'ends': [], 'end_context': [], 'out_of_scope': False,
            'candidates': [{'label': 2, 'designation_idx': 0, 'designation': {'raw': 'VS2-S13-22/S4'},
                            'text': 'VS2-S13-22/S4', 'level': None, 'evidence': [{'kind': 'leader_landing', 'node': 1}]}]}


def test_gemini_is_asked_the_same_question_with_a_json_schema_answer():
    answer = [{'stretch': 4, 'label': 2, 'designation_idx': 0, 'ambiguous': False}]
    models = FakeModels(answer)
    ask = GeminiTransport(SimpleNamespace(models=models), 'gemini-x-pro')
    assert ask([question()]) == answer
    request, = models.requests
    assert request['model'] == 'gemini-x-pro'
    assert request['config'].response_mime_type == 'application/json'
    assert request['config'].response_json_schema['properties']['decisions']['type'] == 'array'
    assert 'VS2-S13-22/S4' in request['contents'][0].parts[-1].text
    used, = ask.usage
    assert (used['tokens_in'], used['tokens_out'], used['cached_tokens']) == (1200, 200, 800)


def test_images_go_as_inline_bytes():
    parts = _parts([{'type': 'input_text', 'text': 'x'},
                    {'type': 'input_image', 'image_url': 'data:image/png;base64,QUJD', 'detail': 'high'}])
    assert parts[0].text == 'x' and parts[1].inline_data.data == b'ABC'
    assert parts[1].inline_data.mime_type == 'image/png'


def test_every_model_is_a_choice_and_unconnected_ones_have_no_transport(monkeypatch):
    for name in ('OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'GEMINI_API_KEY', 'GOOGLE_API_KEY', 'VVS_OPENAI_CONFIG_FILE'):
        monkeypatch.delenv(name, raising=False)
    assert ai_models.CHOICES == ('none', 'gpt-6-astra', 'gpt-6.1-sol', 'claude-opus-5-5', 'claude-fable-5-2', 'gemini-pro')
    assert not any(v for k, v in ai_models.available().items() if k != 'none')
    assert all(ai_models.transport(c) is None for c in ai_models.CHOICES)
    monkeypatch.setenv('VVS_SOL_MODEL', 'gpt-6.1-sol-2026')
    assert ai_models.model_id('gpt-6.1-sol') == 'gpt-6.1-sol-2026'
