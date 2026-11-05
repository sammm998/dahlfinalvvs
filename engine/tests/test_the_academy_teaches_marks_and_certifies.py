"""Dahl Academy från första lektionen till ett verifierbart certifikat.

Provet går hela vägen en människa går: öppna en utbildning, läsa en lektion, mängda ett rör på en ritning, få
rättat, göra quiz, skriva sluttentan, ladda om mitt i den, lämna in, och få ett certifikat som någon annan kan
verifiera utan att logga in.

Två saker prövas hårdare än resten, eftersom hela utbildningens värde hänger på dem:

  * **Facit lämnar aldrig servern.** Inget svar från API:t får innehålla nyckeln till en övning eller en fråga.
  * **Certifikatet kommer från servern.** En klient som påstår sig ha klarat tentan får inget certifikat.
"""

import os
import sys

import pytest


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("academy")
    os.environ["VVS_DATABASE_URL"] = f"sqlite:///{tmp}/ac.db"
    os.environ["VVS_STORAGE_ROOT"] = str(tmp / "storage")
    os.environ["VVS_SECRET_KEY"] = "testtesttest"
    backend = os.path.join(os.path.dirname(__file__), "..", "..", "backend")
    sys.path.insert(0, os.path.abspath(backend))
    for m in list(sys.modules):
        if m.startswith("app"):
            del sys.modules[m]
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c
    for m in list(sys.modules):
        if m.startswith("app"):
            del sys.modules[m]


@pytest.fixture(scope="module")
def H(client):
    r = client.post("/api/auth/register", json={"email": "elev@example.com", "password": "hemligt1"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ---------------------------------------------------------------- innehållet finns

def test_the_content_is_there_after_start(client, H):
    r = client.get("/api/academy/courses", headers=H)
    assert r.status_code == 200, r.text
    kurser = r.json()["kurser"]
    assert len(kurser) >= 3, "minst tre kompletta utbildningar"
    assert sum(k["lektioner"] for k in kurser) >= 20, "minst tjugo lektioner"
    grund = next(k for k in kurser if k["slug"] == "grund-vvs-kalkyl")
    assert grund["moduler"] >= 5


def test_a_course_has_modules_lessons_and_a_lock(client, H):
    r = client.get("/api/academy/courses/grund-vvs-kalkyl", headers=H)
    assert r.status_code == 200
    mods = r.json()["moduler"]
    assert mods[0]["open"] is True, "första modulen är alltid öppen"
    assert any(m["open"] is False for m in mods), "en modul längre fram är låst tills den föregående är klar"
    assert r.json()["tenta"]["slug"] == "fc-certified-vvs"


# ---------------------------------------------------------------- lektion och XP

def test_a_lesson_can_be_read_and_completed_for_xp(client, H):
    c = client.get("/api/academy/courses/grund-vvs-kalkyl", headers=H).json()
    lid = c["moduler"][0]["lektioner"][0]["id"]
    les = client.get(f"/api/academy/lessons/{lid}", headers=H).json()
    assert les["blocks"], "lektionen har innehåll"
    assert les["kurs"]["slug"] == "grund-vvs-kalkyl"
    before = client.get("/api/academy/me", headers=H).json()["xp"]
    done = client.post(f"/api/academy/lessons/{lid}/klar", headers=H).json()
    assert done["xp"] > 0
    assert done["xp_totalt"] > before
    # en andra gång ger inga poäng till: samma sak kan inte ge poäng två gånger
    again = client.post(f"/api/academy/lessons/{lid}/klar", headers=H).json()
    assert again["xp"] == 0


def test_finishing_every_lesson_unlocks_the_next_module(client, H):
    c = client.get("/api/academy/courses/grund-vvs-kalkyl", headers=H).json()
    first, second = c["moduler"][0], c["moduler"][1]
    assert second["open"] is False
    for l in first["lektioner"]:
        client.post(f"/api/academy/lessons/{l['id']}/klar", headers=H)
    c2 = client.get("/api/academy/courses/grund-vvs-kalkyl", headers=H).json()
    assert c2["moduler"][1]["open"] is True, "modul 2 låses upp när modul 1 är klar"


# ---------------------------------------------------------------- övningarna

def test_measuring_a_pipe_on_a_drawing_is_marked_against_the_geometry(client, H):
    from app.academy_plans import BAD
    right = BAD.metres_where(sys="KV")
    scale = BAD.m_per_unit
    # en polyline vars längd ger exakt rätt antal meter
    units = right / scale
    r = client.post("/api/academy/exercises/ov-mangda-kv/forsok",
                    json={"given": {"runs": [[[0, 0], [units, 0]]]}}, headers=H)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["passed"] is True
    assert abs(out["feedback"]["din_mangd"] - right) < 0.05
    assert out["xp"] > 0


def test_a_miss_gets_the_numbers_and_a_reason_not_just_wrong(client, H):
    from app.academy_plans import VARME
    right = VARME.metres_where(sys="VS", dn=20)
    units = (right * 0.90) / VARME.m_per_unit          # tio procent för lite: utanför toleransen
    out = client.post("/api/academy/exercises/ov-mangda-vs20/forsok",
                      json={"given": {"runs": [[[0, 0], [units, 0]]]}}, headers=H).json()
    assert out["passed"] is False
    fb = out["feedback"]
    assert "din_mangd" in fb and "ratt_mangd" in fb and "avvikelse_pct" in fb
    assert "Rätt mängd är" in fb["text"]
    assert out["feedback"]["avvikelse_pct"] < 0
    assert out.get("ledtrad"), "en ledtråd efter ett misslyckat försök"


def test_marking_components_gives_partial_credit_and_names_the_miss(client, H):
    out = client.post("/api/academy/exercises/ov-markera-ventiler/forsok",
                      json={"given": {"picked": ["v-kv-stam", "v-vv-stam"]}}, headers=H).json()
    assert out["passed"] is False
    assert 0 < out["score"] < 1, "två av fyra ger delpoäng"
    assert "missade" in out["feedback"] and out["feedback"]["missade"]
    assert "Avstängning" in out["feedback"]["text"], "den missade ventilen nämns vid namn"


def test_a_calculation_exercise_marks_every_step_on_its_own(client, H):
    out = client.post("/api/academy/exercises/ov-kalkyl-1/forsok",
                      json={"given": {"steps": {"material": "10 200", "timmar": "21,6",
                                                "arbete": "11232", "paslag": "1224", "total": "1"}}},
                      headers=H).json()
    assert out["passed"] is False
    steg = out["feedback"]["steg"]
    assert [s["ok"] for s in steg] == [True, True, True, True, False]
    assert "Total kostnad".lower() in out["feedback"]["text"].lower()
    # svenskt decimalkomma och tusenavskiljande mellanslag ska läsas som tal
    assert steg[1]["ditt"] == 21.6


def test_a_correct_calculation_passes_with_swedish_numbers(client, H):
    out = client.post("/api/academy/exercises/ov-kalkyl-1/forsok",
                      json={"given": {"steps": {"material": "10200", "timmar": "21,6", "arbete": "11 232",
                                                "paslag": "1224", "total": "22656"}}}, headers=H).json()
    assert out["passed"] is True


def test_ordering_and_categorising_are_marked(client, H):
    order = client.post("/api/academy/exercises/ov-bygg-krets/forsok",
                        json={"given": {"order": ["kalla", "pump", "avst", "inj", "rad", "retur"]}},
                        headers=H).json()
    assert order["passed"] is True
    cat = client.post("/api/academy/exercises/ov-kategorisera/forsok",
                      json={"given": {"buckets": {"wc": "sanitet", "tv": "sanitet", "rad": "varme",
                                                  "kv": "ventiler", "gb": "avlopp", "cp": "pumpar",
                                                  "bv": "ventiler", "ek": "varme"}}}, headers=H).json()
    assert cat["passed"] is True


def test_the_whole_room_is_one_exercise_with_several_posts(client, H):
    from app.academy_plans import BAD
    out = client.post("/api/academy/exercises/ov-rum-badrum/forsok",
                      json={"given": {"items": {
                          "kv": BAD.metres_where(sys="KV"), "vv": BAD.metres_where(sys="VV"),
                          "spill": BAD.metres_where(sys="S"), "ventiler": BAD.count_of("kulventil"),
                          "porslin": BAD.count_of("wc", "tvattstall")}}}, headers=H).json()
    assert out["passed"] is True
    assert len(out["feedback"]["poster"]) == 5


# ---------------------------------------------------------------- facit läcker inte

def test_no_answer_key_ever_leaves_the_server(client, H):
    import json
    c = client.get("/api/academy/courses/grund-vvs-kalkyl", headers=H).json()
    lid = c["moduler"][2]["lektioner"][0]["id"]
    les = client.get(f"/api/academy/lessons/{lid}", headers=H).text
    assert '"answer"' not in les
    quiz = client.get("/api/academy/modules/grund-vvs-kalkyl/ritningslasning/quiz", headers=H).text
    assert '"answer"' not in quiz
    # ingen av de kända facitnycklarna får synas i något svar
    for blob in (les, quiz):
        d = json.loads(blob)
        assert "metres" not in json.dumps(d.get("ovningar", []))


def test_the_quiz_is_marked_on_the_server_and_explains(client, H):
    q = client.get("/api/academy/modules/grund-vvs-kalkyl/ritningslasning/quiz?n=4", headers=H).json()
    assert len(q["fragor"]) == 4
    svar = {f["slug"]: 0 for f in q["fragor"]}
    order = {f["slug"]: f["order"] for f in q["fragor"]}
    out = client.post("/api/academy/modules/grund-vvs-kalkyl/ritningslasning/quiz",
                      json={"svar": svar, "order": order}, headers=H).json()
    assert 0.0 <= out["score"] <= 1.0
    assert all("forklaring" in r for r in out["fragor"])


# ---------------------------------------------------------------- sluttentan

def test_the_exam_autosaves_survives_a_reload_and_is_marked_on_the_server(client, H):
    start = client.post("/api/academy/exams/fc-certified-vvs/start", headers=H)
    assert start.status_code == 200, start.text
    att = start.json()
    assert att["status"] == "pagaende"
    assert att["uppgifter"], "tentan har uppgifter"
    assert '"answer"' not in start.text, "tentan skickar aldrig facit"

    first = att["uppgifter"][0]
    client.put(f"/api/academy/exams/attempt/{att['id']}/svar",
               json={"ref": first["slug"], "given": 0}, headers=H)

    # ladda om: samma försök, samma uppgifter, sparade svar kvar
    again = client.get(f"/api/academy/exams/attempt/{att['id']}", headers=H).json()
    assert again["id"] == att["id"]
    assert [u["slug"] for u in again["uppgifter"]] == [u["slug"] for u in att["uppgifter"]]
    assert again["svar"][first["slug"]] == 0

    # att starta igen ger samma pågående försök, inte ett nytt
    assert client.post("/api/academy/exams/fc-certified-vvs/start", headers=H).json()["id"] == att["id"]

    out = client.post(f"/api/academy/exams/attempt/{att['id']}/lamna-in", headers=H).json()
    assert out["passed"] in (True, False)
    assert out["per_omrade"], "resultat per huvudområde"
    # nästan säkert underkänd med ett enda svar: då finns inget certifikat
    if not out["passed"]:
        assert out["certifikat"] is None
        assert out["svaga"], "svaga områden pekas ut"

    # ett inlämnat försök går inte att ändra
    r = client.put(f"/api/academy/exams/attempt/{att['id']}/svar",
                   json={"ref": first["slug"], "given": 1}, headers=H)
    assert r.status_code == 409


def test_a_passed_exam_issues_a_certificate_that_anyone_can_verify(client, H):
    """Rätt svar på allt ger godkänt och ett certifikat. Facit hämtas här ur databasen, inte ur API:t."""
    from app.academy_models import Exercise, ExamAttempt, Question
    from app.db import SessionLocal

    # nytt konto, så det förra försöket inte står i vägen
    reg = client.post("/api/auth/register", json={"email": "duktig@example.com", "password": "hemligt1"})
    HH = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    att = client.post("/api/academy/exams/fc-certified-vvs/start", headers=HH).json()

    with SessionLocal() as db:
        row = db.get(ExamAttempt, att["id"])
        for it in row.items:
            if it["kind"] == "q":
                q = db.query(Question).filter(Question.slug == it["ref"]).first()
                a = q.answer or {}
                given = a.get("index") if q.kind == "single" else (
                    a.get("value") if q.kind in ("bool", "numeric") else a.get("indexes"))
            else:
                e = db.query(Exercise).filter(Exercise.slug == it["ref"]).first()
                a = e.answer or {}
                if e.kind == "mangda":
                    given = {"runs": [[[0, 0], [a["metres"] / (e.data or {}).get("m_per_unit", 0.01), 0]]]}
                elif e.kind in ("markera", "hitta-fel", "ritningsquiz"):
                    given = {"picked": a.get("picked", [])}
                elif e.kind in ("dimension", "symbol"):
                    given = {"index": a.get("index")}
                elif e.kind == "matcha":
                    given = {"pairs": a.get("pairs", {})}
                elif e.kind == "bygg":
                    given = {"order": a.get("order", [])}
                elif e.kind == "kalkyl":
                    given = {"steps": a.get("steps", {})}
                elif e.kind == "numerisk":
                    given = {"value": a.get("value")}
                elif e.kind == "kategorisera":
                    given = {"buckets": a.get("buckets", {})}
                elif e.kind == "rum":
                    given = {"items": a.get("items", {})}
                else:
                    given = {}
            client.put(f"/api/academy/exams/attempt/{att['id']}/svar",
                       json={"ref": it["ref"], "given": given}, headers=HH)

    out = client.post(f"/api/academy/exams/attempt/{att['id']}/lamna-in", headers=HH).json()
    assert out["passed"] is True, out
    assert out["score"] >= 0.8
    code = out["certifikat"]
    assert code and code.startswith("FC-VVS-") and len(code) == 15

    mine = client.get("/api/academy/certificates", headers=HH).json()["certifikat"]
    assert any(c["code"] == code for c in mine)

    # verifieringen är öppen och visar bara det som behövs för att lita på certifikatet
    v = client.get(f"/api/public/certificate/{code}")
    assert v.status_code == 200
    body = v.json()
    assert body["giltigt"] is True
    assert body["code"] == code
    assert "example.com" not in v.text, "ingen e-post i en öppen verifiering"
    assert "score" not in body and "per_omrade" not in body

    assert client.get("/api/public/certificate/FC-VVS-FINNSINTE").json()["giltigt"] is False


def test_progress_survives_a_new_session(client, H):
    """Logga ut och in igen: framstegen ligger på kontot, inte i webbläsaren."""
    before = client.get("/api/academy/me", headers=H).json()
    tok = client.post("/api/auth/login", data={"username": "elev@example.com", "password": "hemligt1"})
    assert tok.status_code == 200, tok.text
    H2 = {"Authorization": f"Bearer {tok.json()['access_token']}"}
    after = client.get("/api/academy/me", headers=H2).json()
    assert after["xp"] == before["xp"]
    assert after["kurser"][0]["klara"] == before["kurser"][0]["klara"]
    assert after["niva"]["namn"]


def test_the_dashboard_says_where_to_continue(client, H):
    me = client.get("/api/academy/me", headers=H).json()
    assert me["fortsatt"], "dashboarden pekar på nästa lektion"
    assert me["fortsatt"]["lektion"]
    assert me["ovningar"]["gjorda"] >= 1
    assert me["aktivitet"], "senaste aktiviteten syns"
