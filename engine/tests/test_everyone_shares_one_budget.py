"""Alla konton delar en budget: 10 000 kr för det som kostar pengar, och alla som loggar in ser den.

Ingen köper credits och ingen läsning dras från ett eget saldo. Det som faktiskt kostar - anropen till
språkmodellerna - dras från en gemensam budget, och sidan Credits visar samma sak för alla: taket, vad som gått åt,
vad som är kvar, till vad och av vem.
"""
import os
import sys
import time

import pymupdf
import pytest


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("credits")
    os.environ["VVS_DATABASE_URL"] = f"sqlite:///{tmp}/test.db"
    os.environ["VVS_STORAGE_ROOT"] = str(tmp / "storage")
    os.environ["VVS_SECRET_KEY"] = "test"
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))
    for m in list(sys.modules):
        if m.startswith("app"):
            del sys.modules[m]
    from fastapi.testclient import TestClient
    from app.main import app
    from source_service_double import offline_source_service
    with offline_source_service(), TestClient(app) as c:
        yield c


def _user(client, email):
    r = client.post("/api/auth/register", json={"email": email, "password": "hemligt1"}).json()
    return {"Authorization": f"Bearer {r['access_token']}"}, r["role"]


def _upload(client, H, path, name="plan.pdf"):
    p = client.post("/api/projects", json={"name": "Kv Budget", "description": ""}, headers=H).json()
    with open(path, "rb") as fh:
        return client.post(f"/api/projects/{p['id']}/drawings", files={"file": (name, fh, "application/pdf")},
                           headers=H).json()


def test_everyone_sees_the_same_shared_budget(client):
    Ha, role = _user(client, "drift@example.com")
    assert role == "admin"
    Hk, _ = _user(client, "kund@example.com")
    a = client.get("/api/credits", headers=Ha).json()
    k = client.get("/api/credits", headers=Hk).json()
    assert a["shared"] and k["shared"] and a["budget"]["limit_kr"] == 10000.0
    assert a["budget"]["remaining_kr"] == k["budget"]["remaining_kr"] == a["balance"]
    assert k["me"] == "kund@example.com"
    for key in ("spent_kr", "by_source", "by_user", "by_model", "recent", "requests"):
        assert key in k["budget"]


def test_ai_use_is_drawn_from_the_shared_budget_with_who_used_it(client):
    Hk, _ = _user(client, "anvandare@example.com")
    from app import api_budget
    from app.db import SessionLocal, User
    with SessionLocal() as db:
        uid = db.query(User).filter(User.email == "anvandare@example.com").one().id
    token = api_budget.WHO.set(uid)
    try:
        assert api_budget.charge("gpt-6.1-sol", tokens_in=100000, tokens_out=20000, source="agent") > 0
    finally:
        api_budget.WHO.reset(token)
    b = client.get("/api/credits", headers=Hk).json()["budget"]
    assert b["spent_kr"] > 0 and b["remaining_kr"] < 10000.0
    assert any(r["key"] == "anvandare@example.com" and r["kr"] > 0 for r in b["by_user"])
    assert b["recent"][0]["user"] == "anvandare@example.com" and b["recent"][0]["source"] == "agent"
    Hother, _ = _user(client, "annan@example.com")
    assert client.get("/api/credits", headers=Hother).json()["budget"]["spent_kr"] == b["spent_kr"]


def test_credits_cannot_be_bought_and_a_reading_draws_nothing(client, source_api_pdf):
    Hk, _ = _user(client, "kopare@example.com")
    # köpet, paketen och prislistan finns inte längre
    assert client.post("/api/credits/purchase", json={"package_id": "start"}, headers=Hk).status_code in (404, 405)
    assert client.get("/api/public/pricing").status_code in (404, 405) or "packages" not in client.get("/api/public/pricing").text
    d = _upload(client, Hk, source_api_pdf)
    price = client.get(f"/api/drawings/{d['id']}/price", headers=Hk).json()
    assert price["exempt"] and price["enough"]
    j = client.post(f"/api/drawings/{d['id']}/analyze", headers=Hk)
    assert j.status_code == 200, j.text
    assert not j.json().get("charged")


def test_a_message_from_the_contact_page_reaches_the_administrator(client):
    r = client.post("/api/public/contact", json={"name": "Anna", "email": "anna@example.com", "company": "Rör AB",
                                                 "subject": "Demo", "message": "Vi vill se systemet på en av våra handlingar."})
    assert r.status_code == 200 and r.json()["ok"]
    assert client.post("/api/public/contact", json={"name": "x", "email": "x@example.com", "message": "hej"}).status_code == 422
    a = client.post("/api/auth/login", data={"username": "drift@example.com", "password": "hemligt1"}).json()
    Ha = {"Authorization": f"Bearer {a['access_token']}"}
    rows = client.get("/api/admin/contact", headers=Ha).json()["rows"]
    assert rows and rows[0]["email"] == "anna@example.com" and rows[0]["status"] == "ny"
    assert client.put(f"/api/admin/contact/{rows[0]['id']}", json={"status": "besvarad"}, headers=Ha).json()["status"] == "besvarad"


def _wait(client, H, job_id):
    import time
    for _ in range(240):
        j = client.get(f"/api/jobs/{job_id}", headers=H).json()
        if j["status"] in ("COMPLETED", "FAILED"):
            return j
        time.sleep(0.5)
    raise AssertionError("jobbet blev aldrig klart")


class _Seen:
    def as_dict(self):
        return {"findings": []}


def test_a_request_that_asks_the_ai_is_put_on_the_person_who_asked(client, source_api_pdf, monkeypatch):
    """Hela vägen: inloggningen i anropet -> mellanledet -> mätaren -> raden i reskontran -> sidan Credits."""
    Hb, _ = _user(client, "fragare@example.com")
    d = _upload(client, Hb, source_api_pdf)
    j = _wait(client, Hb, client.post(f"/api/drawings/{d['id']}/analyze", headers=Hb).json()["id"])
    assert j["status"] == "COMPLETED", j
    from tools import meter
    import tools.readers
    import vvs_engine.review.vision as vz

    def look(pa, doc, ask=None):
        meter.after("gpt-6.1-sol", {"input_tokens": 40000, "output_tokens": 4000}, "vision")
        return _Seen()
    monkeypatch.setattr(vz, "look", look)
    monkeypatch.setattr(tools.readers, "vision", lambda *a, **k: None)
    before = client.get("/api/credits", headers=Hb).json()["budget"]["spent_kr"]
    r = client.post(f"/api/jobs/{j['id']}/vision?page=0", headers=Hb)
    assert r.status_code == 200, r.text
    Ha, _ = _user(client, "tittare@example.com")
    b = client.get("/api/credits", headers=Ha).json()["budget"]   # en annan inloggning ser samma sak
    assert b["spent_kr"] > before
    assert b["recent"][0]["user"] == "fragare@example.com" and b["recent"][0]["source"] == "vision"
    assert any(u["key"] == "fragare@example.com" for u in b["by_user"])
    assert any(s["key"] == "vision" for s in b["by_source"])


def test_a_job_in_a_pool_thread_knows_whose_it_is():
    """En pooltråd ärver inte anropets sammanhang; kopian som jobs.py och projects_api.py skickar med gör det."""
    import contextvars
    from app import api_budget
    from app.jobs import _reader
    tok = api_budget.WHO.set("u-123")
    try:
        assert _reader.submit(contextvars.copy_context().run, api_budget.WHO.get).result() == "u-123"
    finally:
        api_budget.WHO.reset(tok)


def test_when_the_budget_is_spent_the_ai_stops_for_everyone_and_everyone_sees_it(client):
    r = client.post("/api/auth/login", data={"username": "drift@example.com", "password": "hemligt1"}).json()
    Ha = {"Authorization": f"Bearer {r['access_token']}"}
    Hk, _ = _user(client, "sist@example.com")
    spent = client.get("/api/credits", headers=Hk).json()["budget"]["spent_kr"]
    assert spent > 0
    assert client.put("/api/admin/api-budget", json={"limit_kr": spent / 2}, headers=Hk).status_code == 403
    assert client.put("/api/admin/api-budget", json={"limit_kr": spent / 2}, headers=Ha).status_code == 200
    try:
        b = client.get("/api/credits", headers=Hk).json()["budget"]
        assert b["exhausted"] and b["remaining_kr"] == 0
        from app import api_budget
        assert api_budget.blocked("gpt-6.1-sol") == api_budget.EXHAUSTED
    finally:
        client.put("/api/admin/api-budget", json={"limit_kr": 10000}, headers=Ha)
    assert not client.get("/api/credits", headers=Hk).json()["budget"]["exhausted"]


def test_a_bad_login_is_refused_and_never_breaks_the_request(client):
    assert client.get("/api/credits", headers={"Authorization": "Bearer inte-en-token"}).status_code == 401
    assert client.get("/api/credits").status_code == 401


def _admin(client):
    r = client.post("/api/auth/login", data={"username": "drift@example.com", "password": "hemligt1"}).json()
    return {"Authorization": f"Bearer {r['access_token']}"}


def test_the_shared_budget_started_once_at_10000_kr(client):
    from app import api_budget
    from app.db import SessionLocal
    with SessionLocal() as db:
        cfg = api_budget.settings_of(db)
        assert cfg["limit_kr"] == 10000.0 and cfg["reset_at"]          # en ny räkning när budgeten startade
        assert api_budget.shared_start(db) is False                      # och bara en gång
    Ha = _admin(client)
    for path in ("/api/admin/pricing", "/api/admin/credits"):
        assert client.get(path, headers=Ha).status_code in (404, 405)


def test_filters_and_csv_show_the_same_rows(client):
    Hk, _ = _user(client, "filter@example.com")
    b = client.get("/api/credits", params={"who": "fragare@example.com"}, headers=Hk).json()["budget"]
    assert b["recent"] and all(r["user"] == "fragare@example.com" for r in b["recent"])
    assert [u["key"] for u in b["by_user"]] == ["fragare@example.com"]
    assert "fragare@example.com" in b["people"] and any(s["key"] == "vision" for s in b["sources"])
    whole = client.get("/api/credits", headers=Hk).json()["budget"]
    assert b["spent_kr"] == whole["spent_kr"]                           # taket och det använda gäller hela perioden
    assert b["filtered"]["kr"] <= whole["filtered"]["kr"]
    v = client.get("/api/credits", params={"source": "agent"}, headers=Hk).json()["budget"]
    assert v["recent"] and all(r["source"] == "agent" and r["label"] == "Agenten" for r in v["recent"])
    future = client.get("/api/credits", params={"since": "2999-01-01"}, headers=Hk).json()["budget"]
    assert future["recent"] == [] and future["filtered"]["requests"] == 0
    assert client.get("/api/credits", params={"since": "igår"}, headers=Hk).status_code == 422
    csv = client.get("/api/credits.csv", params={"who": "fragare@example.com"}, headers=Hk)
    assert csv.status_code == 200 and csv.headers["content-type"].startswith("text/csv")
    lines = csv.text.lstrip("\ufeff").strip().splitlines()
    assert lines[0].startswith("Tid;Vem;Till vad") and len(lines) - 1 == b["filtered"]["requests"]
    assert all(";fragare@example.com;" in ln for ln in lines[1:])


def test_the_voice_call_is_counted_with_its_audio_price_and_who_spoke(client, source_api_pdf):
    Hb, _ = _user(client, "pratare@example.com")
    d = _upload(client, Hb, source_api_pdf)
    j = _wait(client, Hb, client.post(f"/api/drawings/{d['id']}/analyze", headers=Hb).json()["id"])
    usage = {"input_tokens": 3000, "output_tokens": 1200,
             "input_token_details": {"audio_tokens": 2500, "text_tokens": 500, "cached_tokens": 0},
             "output_token_details": {"audio_tokens": 1000, "text_tokens": 200}}
    r = client.post(f"/api/jobs/{j['id']}/live/usage", json={"kind": "response", "usage": usage}, headers=Hb).json()
    # 500 text in à 4 + 2500 ljud in à 32 + 200 text ut à 16 + 1000 ljud ut à 64 USD per miljon, gånger kursen
    from app import api_budget
    assert abs(r["kr"] - (500 * 4 + 2500 * 32 + 200 * 16 + 1000 * 64) / 1e6 * api_budget.USD_SEK_DEFAULT) < 0.01
    assert r["exhausted"] is False
    t = client.post(f"/api/jobs/{j['id']}/live/usage",
                    json={"kind": "transcription", "usage": {"input_tokens": 800, "output_tokens": 40}}, headers=Hb).json()
    assert t["kr"] > 0
    b = client.get("/api/credits", params={"who": "pratare@example.com"}, headers=Hb).json()["budget"]
    assert {s["key"] for s in b["by_source"]} == {"röst", "röst_transkribering"}
    assert {s["label"] for s in b["by_source"]} == {"Röstsamtal", "Röstsamtal – transkribering"}
    # någon annans samtal går inte att bokföra på
    Hx, _ = _user(client, "utomstaende@example.com")
    assert client.post(f"/api/jobs/{j['id']}/live/usage", json={"usage": usage}, headers=Hx).status_code == 404
    # ett orimligt tal från webbläsaren tas inte emot som det är
    big = client.post(f"/api/jobs/{j['id']}/live/usage", json={"usage": {"input_tokens": 10**12}}, headers=Hb).json()
    assert big["kr"] < 100


def test_everyone_is_warned_from_80_percent_and_the_admins_are_told_once_per_level(client):
    Ha = _admin(client)
    Hk, _ = _user(client, "varnad@example.com")
    spent = client.get("/api/credits", headers=Hk).json()["budget"]["spent_kr"]
    from app import api_budget
    try:
        client.put("/api/admin/api-budget", json={"limit_kr": round(spent / 0.82, 4)}, headers=Ha)
        b = client.get("/api/credits", headers=Hk).json()["budget"]
        assert b["warning"] == 80 and not b["exhausted"]
        api_budget.charge("gpt-6.1-sol", tokens_in=10, tokens_out=1, source="agent")
        api_budget.charge("gpt-6.1-sol", tokens_in=10, tokens_out=1, source="agent")
        msgs = [m for m in client.get("/api/admin/contact", headers=Ha).json()["rows"] if "AI-budget" in m["subject"]]
        assert [m["subject"] for m in msgs] == ["AI-budgeten: 80 % använd"]       # en gång, inte per anrop
        client.put("/api/admin/api-budget", json={"limit_kr": round(spent / 0.97, 4)}, headers=Ha)
        assert client.get("/api/credits", headers=Hk).json()["budget"]["warning"] == 95
        api_budget.charge("gpt-6.1-sol", tokens_in=10, tokens_out=1, source="agent")
        subjects = [m["subject"] for m in client.get("/api/admin/contact", headers=Ha).json()["rows"]]
        assert "AI-budgeten: 95 % använd" in subjects
    finally:
        client.put("/api/admin/api-budget", json={"limit_kr": 10000}, headers=Ha)
    assert client.get("/api/credits", headers=Hk).json()["budget"]["warning"] == 0


def test_the_warning_is_mailed_to_the_admins_when_smtp_is_set(client, monkeypatch):
    sent = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            sent.append(("connect", host, port))
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def starttls(self):
            sent.append(("tls",))
        def login(self, u, p):
            sent.append(("login", u))
        def send_message(self, msg):
            sent.append(("msg", msg["To"], msg["Subject"]))
    import smtplib
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    monkeypatch.setenv("VVS_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("VVS_SMTP_USER", "larm")
    from app import api_budget
    from app.db import SessionLocal
    with SessionLocal() as db:
        n = api_budget._mail_admins(db, "AI-budgeten: 80 % använd", "text")
    assert n >= 1 and ("connect", "smtp.example.com", 587) in sent and ("login", "larm") in sent
    assert any(x[0] == "msg" and "drift@example.com" in x[1] for x in sent)
    monkeypatch.delenv("VVS_SMTP_HOST")
    with SessionLocal() as db:
        assert api_budget._mail_admins(db, "x", "y") == 0          # utan SMTP: bara meddelandet i Administration
