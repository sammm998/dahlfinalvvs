"""AI-kontrollen av en teknisk beskrivning: billig, och kan inte hitta på något.

Modellen får bara raderna som inte blev en post men nämner en produkt, och bara posterna med flera kandidater i
katalogen. Ett svar som säger något som inte står på raden kastas, ett val utanför kandidatlistan kastas, och
samma fråga två gånger kostar ingenting. Ingenting ändrar ett antal: missade produkter är förslag som en
människa godkänner.
"""
from __future__ import annotations

import os
import re
import sys

import pymupdf
import pytest

from vvs_engine.tb import ai, read_tech_spec

sys.path.insert(0, os.path.dirname(__file__))
from test_a_technical_description_is_read_to_its_materials import PAGES, _page  # noqa: E402

EXTRA = [("ama", "PS", "SPRINKLER M.M."),
         ("text", "Märkning av ventiler med skyltar fabr. Brady typ B-7593, gravyr 40x20 mm."),
         ("text", "Mineralull får ej vara cancerklassad enligt KIFS 2001:3."),
         ("text", "Rören provtrycks enligt SS-EN 806-4 och AMA VVS 22.")]


def _doc():
    pages = PAGES + [EXTRA]
    doc = pymupdf.open()
    for i, rows in enumerate(pages):
        _page(doc, rows, i + 1, len(pages))
    return doc


def test_only_the_lines_that_name_a_product_and_are_not_a_post_are_sent():
    doc = _doc()
    items = read_tech_spec(doc)["items"]
    lines = ai.residual_lines(doc, items)
    text = " ".join(ln["text"] for ln in lines)
    own = [ln["text"].split(" / ")[0] for ln in lines]      # raden själv, utan nästa rad som sammanhang
    assert "Brady" in text                                  # en produkt i kravtexten som inte blev en post
    assert not any("KIFS" in t or "SS-EN 806" in t for t in own)   # standarder är inga produkter
    assert "B202B" not in text                              # posterna är redan lästa
    whole = sum(len(p.get_text()) for p in doc)
    assert sum(len(ln["text"]) for ln in lines) < 0.2 * whole   # en bråkdel av dokumentet går till modellen
    assert len(ai.missed_batches(lines)) == 1


def test_an_answer_that_is_not_on_the_line_is_thrown_away():
    lines = [{"page": 4, "text": "Märkning av ventiler med skyltar fabr. Brady typ B-7593, gravyr 40x20 mm."}]
    found = [
        {"line": 1, "name": "Skylt", "manufacturer": "Brady", "type": "B-7593", "rsk": ""},          # står där
        {"line": 1, "name": "Skylt", "manufacturer": "Hellermann", "type": "X1", "rsk": ""},        # påhittat
        {"line": 1, "name": "Skylt", "manufacturer": "Brady", "type": "B-7593", "rsk": "1234567"},  # nummer saknas
        {"line": 9, "name": "Ingen rad", "manufacturer": "Brady", "type": "", "rsk": ""},           # ingen sådan rad
        {"line": 1, "name": "", "manufacturer": "", "type": "", "rsk": ""},                         # inget alls
    ]
    got = ai.accept_missed(found, lines, items=[])
    assert len(got) == 1 and got[0]["manufacturer_text"] == "Brady" and got[0]["type"] == "B-7593"
    assert got[0]["rsk"] == "" and got[0]["page"] == 4
    # det som redan är en post föreslås inte igen
    assert ai.accept_missed(found[:1], lines, items=[{"manufacturer": "Brady", "type": "B-7593"}]) == []


def _post(i, hits, status="möjlig", rsk=None):
    return {"id": f"p{i}", "name": f"Vara {i}", "manufacturer": "Nibe", "type": "Eminent 55", "text": "", "spec": {},
            "rsk": [], "match": {"status": status, "hits": hits, "rsk": rsk}}


H = [{"ref": "6944311", "name": "Varmvattenberedare Eminent-R 55"},
     {"ref": "6944312", "name": "Varmvattenberedare Eminent CU 55"}]


def test_only_uncertain_posts_are_asked_and_a_pick_must_be_a_real_candidate():
    items = [_post(0, H), _post(1, H), _post(2, H[:1]), _post(3, H, status="hittad"), _post(4, H, status="saknas")]
    batches = ai.pick_batches(items)
    assert [it["id"] for it in batches[0][0]] == ["p0", "p1"]      # en träff, hittad och saknas frågas inte

    def ask(instructions, payload, schema):
        assert "P0:" in payload and "0: 6944311" in payload
        return {"picks": [{"i": 0, "c": 1, "sure": True}, {"i": 1, "c": 7, "sure": True}, {"i": 5, "c": 0, "sure": True}]}
    r = ai.find_picks(items, ask)
    assert r["picks"] == {"p0": {"ref": "6944312", "name": "Varmvattenberedare Eminent CU 55", "sure": True}}
    assert r["calls"] == 1 and r["asked"] == 2


def test_a_size_family_counts_its_variants_as_candidates():
    rsk = {"kind": "storlek", "variants": [{"rsk": "1111111", "name": "15 AT 4003A15"}, {"rsk": "2222222", "name": "20 AT 4003A20"}]}
    it = _post(0, [], rsk=rsk)
    assert ai.needs_pick(it) and [c["ref"] for c in ai._candidates(it["match"])] == ["1111111", "2222222"]


# ---------------------------------------------------------------- genom tjänsten

@pytest.fixture(scope="module")
def client(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("tbai")
    os.environ["VVS_DATABASE_URL"] = f"sqlite:///{tmp}/test.db"
    os.environ["VVS_STORAGE_ROOT"] = str(tmp / "storage")
    os.environ["VVS_SECRET_KEY"] = "test"
    backend = os.path.join(os.path.dirname(__file__), "..", "..", "backend")
    sys.path.insert(0, os.path.abspath(backend))
    for m in list(sys.modules):
        if m.startswith("app"):
            del sys.modules[m]
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c


def _login(client, email):
    r = client.post("/api/auth/register", json={"email": email, "password": "hemligt1"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_the_check_runs_once_costs_little_and_a_found_product_becomes_a_post_when_accepted(client, monkeypatch):
    _login(client, "admin@example.com")
    H_ = _login(client, "kalkyl@example.com")
    from app import tb_ai
    calls = []

    def fake(instructions, payload, schema, model):
        calls.append((instructions[:20], len(payload)))
        if "found" in schema["properties"]:
            n = next((int(r.split("|")[0]) for r in payload.splitlines() if "Brady" in r), None)
            if n is None:                     # Brady är redan en post: inget att föreslå
                return {"found": []}, {"in": 300, "out": 10, "cached": 0}
            return ({"found": [{"line": n, "name": "Ventilskylt", "manufacturer": "Brady", "type": "B-7593", "rsk": ""},
                               {"line": n, "name": "Påhitt", "manufacturer": "Acme", "type": "Z9", "rsk": ""}]},
                    {"in": 900, "out": 120, "cached": 0})
        picks = [{"i": int(m), "c": 0, "sure": False} for m in re.findall(r"^P(\d+):", payload, re.M)]
        return {"picks": picks}, {"in": 2500, "out": 200, "cached": 0}
    monkeypatch.setattr(tb_ai, "TRANSPORT", fake)

    p = client.post("/api/projects", json={"name": "Tvätthall", "contract_form": "ABT06", "tech_spec": True}, headers=H_).json()
    doc = _doc()
    s = client.post(f"/api/projects/{p['id']}/tech-specs", files={"file": ("tb.pdf", doc.tobytes(), "application/pdf")},
                    headers=H_).json()
    r = client.post(f"/api/tech-specs/{s['id']}/ai", headers=H_)
    assert r.status_code == 200, r.text
    a = r.json()
    assert a["status"] == "COMPLETED" and a["calls"] == len(calls) >= 1 and a["kr"] > 0
    assert a["kr"] < 1.0                                          # öre, inte kronor, för en hel beskrivning
    assert [m["manufacturer_text"] for m in a["missed"]] == ["Brady"]    # det påhittade kastades
    # kostnaden står i den gemensamma budgeten, med vem och till vad
    b = client.get("/api/credits", params={"source": "tb"}, headers=H_).json()["budget"]
    assert b["recent"][0]["user"] == "kalkyl@example.com" and b["recent"][0]["label"] == "Teknisk beskrivning (AI)"

    # samma beskrivning en gång till: ur cachen, utan anrop och utan kostnad
    n = len(calls)
    again = client.post(f"/api/tech-specs/{s['id']}/ai", headers=H_).json()
    assert len(calls) == n and again["calls"] == 0 and again["cached_calls"] >= 1 and again["kr"] == 0

    got = client.get(f"/api/tech-specs/{s['id']}", headers=H_).json()
    chosen = [it for it in got["items"] if it["match"].get("ai")]
    assert all(it["match"]["rsk"]["kind"] == "ai" for it in chosen)
    assert all(it["match"]["ai"]["ref"] in [h["ref"] for h in it["match"]["hits"]] + [
        v["rsk"] for v in (it["match"]["rsk"].get("variants") or [])] for it in chosen)
    before = len(got["items"])

    key = a["missed"][0]["key"]
    after = client.post(f"/api/tech-specs/{s['id']}/ai/missed/{key}", json={"accept": True}, headers=H_).json()
    assert after["missed"] == [] and after["accepted"] == 1
    got = client.get(f"/api/tech-specs/{s['id']}", headers=H_).json()
    new = [it for it in got["items"] if it["id"] == f"ai-{key}"]
    assert len(got["items"]) == before + 1 and new and new[0]["quantity"] is None
    assert new[0]["manufacturer_text"] == "Brady" and "godkänt av kalkyl@example.com" in new[0]["inferred"]
    # en ny körning tar inte tillbaka det som redan godkänts, och den godkända skickas inte igen
    rr = client.post(f"/api/tech-specs/{s['id']}/ai", headers=H_)
    assert rr.status_code == 200, rr.text
    rerun = rr.json()
    assert rerun["missed"] == [] and rerun["accepted"] == 1

    other = _login(client, "annan@example.com")
    assert client.post(f"/api/tech-specs/{s['id']}/ai", headers=other).status_code == 404


def test_no_check_runs_when_the_shared_budget_is_spent(client, monkeypatch):
    H_ = _login(client, "slut@example.com")
    from app import api_budget, tb_ai
    monkeypatch.setattr(tb_ai, "TRANSPORT", lambda *a: pytest.fail("ingen fråga när budgeten är slut"))
    p = client.post("/api/projects", json={"name": "X", "contract_form": "ABT06", "tech_spec": True}, headers=H_).json()
    doc = _doc()
    doc.new_page().insert_text((50, 50), "annan fil", fontname="helv", fontsize=8)
    s = client.post(f"/api/projects/{p['id']}/tech-specs", files={"file": ("b.pdf", doc.tobytes(), "application/pdf")},
                    headers=H_).json()
    monkeypatch.setattr(api_budget, "blocked", lambda *a, **k: api_budget.EXHAUSTED)
    r = client.post(f"/api/tech-specs/{s['id']}/ai", headers=H_)
    assert r.status_code == 402 and "förbrukade" in r.json()["detail"]


def test_the_request_is_built_to_be_cheap(client, monkeypatch):
    """Billigaste modellen, låg resonemangsnivå, ett strikt schema, promptcache och inget sparat hos leverantören.
    En modell som inte tar resonemangsnivå får samma fråga utan."""
    from app import tb_ai
    sent = []

    class R:
        output_text = '{"found": []}'
        usage = type("U", (), {"input_tokens": 700, "output_tokens": 30,
                               "input_tokens_details": type("D", (), {"cached_tokens": 512})()})()

    class Responses:
        def create(self, **kw):
            sent.append(kw)
            if len(sent) == 1:
                raise ValueError("Unsupported parameter: 'reasoning.effort'")
            return R()
    monkeypatch.setattr(tb_ai, "_client", lambda: type("C", (), {"responses": Responses()})())
    answer, usage = tb_ai._openai_ask(ai.MISSED_INSTRUCTIONS, "1|s1|rad", ai.MISSED_SCHEMA, tb_ai.model())
    assert answer == {"found": []} and usage == {"in": 700, "out": 30, "cached": 512}
    first, second = sent
    assert first["model"] == "gpt-6.1-sol" and first["reasoning"] == {"effort": "low"} and first["store"] is False
    assert first["text"]["format"]["strict"] is True and first["prompt_cache_key"].startswith("tb-ai-")
    assert first["input"][0]["content"] == ai.MISSED_INSTRUCTIONS           # det fasta först: cachebart
    assert "reasoning" not in second and second["input"] == first["input"]
