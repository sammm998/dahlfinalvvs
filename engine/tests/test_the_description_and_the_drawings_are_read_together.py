"""AB 04: beskrivningen och ritningarna läses tillsammans och korsrefereras.

Beskrivningen anger krav, produkter och ibland mängder; ritningen har ofta de faktiska mängderna. Ett objekt räknas
en gång. "Antal enligt ritning" hämtar ritningens antal. En motsägelse (10 WC i beskrivningen, 12 på ritningen)
avgörs inte av systemet - den flaggas. R20 är en reglerbar mängd: kalkylen räknar 20. Optioner särredovisas.
Förutsättningar och gränsdragning samlas för sig, och en förfrågan bär hela kravtexten.
"""
from __future__ import annotations

from vvs_engine import offer as OF
from vvs_engine.tb import joint as J
from vvs_engine.tb.mail import drafts_by_maker


def _it(**kw):
    base = {"id": "p1", "code": "", "kind": "post", "name": "WC-stol", "quantity": 10.0, "total_quantity": 10.0,
            "unit": "st", "quantity_text": "10 st", "text": "WC-stol vägghängd.", "page": 4, "ama_code": "PUB.2",
            "manufacturer": "Gustavsberg", "type": "Nautic", "rsk": [], "art_nr": [], "spec": {}, "category": "WC",
            "subcategory": "WC-stolar", "section": ""}
    return {**base, **kw}


def _fd(n, tag="WC01"):
    return {"kind": "antal", "quantity": float(n), "unit": "st", "tag": tag, "sheets": {"V-50-1 blad 2": int(n)}}


def test_a_quantity_the_drawing_confirms_is_counted_once_with_both_sources():
    q = J.quantity(_it(), _fd(10))
    assert q["total_quantity"] == 10 and q["quantity_source"] == "beskrivning, bekräftad av ritning"
    assert [t["kind"] for t in q["quantity_trace"]] == ["beskrivning", "ritning"] and not q["quantity_conflict"]
    assert q["quantity_trace"][1]["sheets"] == {"V-50-1 blad 2": 10}               # vilken ritning


def test_a_conflict_is_flagged_not_resolved():
    q = J.quantity(_it(), _fd(12))
    assert q["quantity_conflict"] == {"beskrivning": 10.0, "ritning": 12.0, "unit_description": "st", "unit_drawing": "st"}
    assert q["total_quantity"] == 10 and "motstridig" in q["quantity_source"]
    assert any("motstridig mängd: beskrivningen 10, ritningen 12" in f for f in q["quantity_flags"])
    # handlingarnas prioriteringsordning kan anges för projektet - flaggan står kvar
    r = J.quantity(_it(), _fd(12), "ritning")
    assert r["total_quantity"] == 12 and r["quantity_source"] == "ritning (prioriteringsordning)" and r["quantity_flags"]


def test_by_drawing_takes_the_drawing_count_and_says_when_it_is_missing():
    it = _it(code="KVP01", name="Cirkulationspump KVP01", quantity=None, total_quantity=None, quantity_text="Enl ritn")
    q = J.quantity(it, _fd(2, "KVP01"))
    assert q["by_drawing"] and q["total_quantity"] == 2 and q["quantity_source"] == "ritning (beskrivningen hänvisar dit)"
    miss = J.quantity(it, None)
    assert miss["total_quantity"] is None and any("enligt ritning" in f for f in miss["quantity_flags"])


def test_r20_is_an_adjustable_quantity_of_twenty():
    q = J.quantity(_it(quantity=None, total_quantity=None, quantity_text="R20"), None)
    assert q["total_quantity"] == 20 and q["adjustable"]["as_written"] == "R20"
    assert q["quantity_source"] == "beskrivning (reglerbar)" and "regleras" in q["quantity_flags"][0]


def test_options_functions_and_references():
    assert J.is_option(_it(text="Som option offereras golvvärme i entréhall."))
    assert J.is_option(_it(ama_code="PUB.21"), {"PUB.2"}) and not J.is_option(_it())
    func = _it(name="Automatisk toppavluftare", text="Automatisk toppavluftare med minikulventil.", manufacturer="", type="")
    assert J.article_status(func) == "funktion - artikel ej föreskriven" and J.article_status(_it()) == "föreskriven"
    assert J.article_status(_it(rsk=["7606418"])) == "föreskriven"
    it = _it(ama_code="PRE.2", text="Pumpar enligt PPC.61. Antal enligt ritning.")
    refs = J.references(it, {"PPC.61": "Pumpar ska vara frekvensstyrda, PN10, med larmutgång."})
    assert refs == [{"code": "PPC.61", "text": "Pumpar ska vara frekvensstyrda, PN10, med larmutgång."}]
    txt = J.inquiry_text(it, [{"text": "Vattentryck i förbindelsepunkt är 6-10 bar."}], refs)
    assert "Pumpar enligt PPC.61" in txt and "frekvensstyrda" in txt and "6-10 bar" in txt


BLOCKS = [
    {"code": "AFC.1", "title": "Entreprenadform", "page": 1, "text": "Entreprenaden utförs som utförandeentreprenad enligt AB 04."},
    {"code": "52.BC", "title": "Varmvattensystem", "page": 2,
     "text": "Lägsta tillåtna varmvattentemperatur vid tappställe är 55°C. Vattentryck i förbindelsepunkt är 6-10 bar."},
    {"code": "YHB.1", "title": "Rumsklimat", "page": 2, "text": "Rumstemperaturen ska vara minst 21 °C i lägenheter."},
    {"code": "PUB.4", "title": "Diskbänkar", "page": 3,
     "text": "Diskbänk och vattenlås levereras av byggentreprenören. Diskbänk ansluts av denna entreprenör. "
             "Vattenmätare tillhandahålls av kommunen. Golvvärme i entré ingår ej."},
    {"code": "PUB.9", "title": "Option tvättställ", "page": 4, "text": "Som option prissätts tvättställ i förråd."},
]


def test_the_whole_description_gives_conditions_boundaries_options_and_contract():
    a = J.analyse(BLOCKS)
    assert a["contract"] == {"AB04": 1, "ABT06": 0, "guess": "AB04", "sure": True}
    kinds = {(c["kind"], c["ama"]) for c in a["conditions"]}
    assert ("temperatur", "52.BC") in kinds and ("temperatur", "YHB.1") in kinds
    room = next(c for c in a["conditions"] if c["ama"] == "YHB.1")
    assert room["requirement"] and "21 °C" in room["values"]
    # krav på minst 21 °C följer med en termostat, så att den inte väljs med en gräns på 20 °C
    thermo = _it(name="Radiatortermostat", category="Termostater", ama_code="PNB.5", text="Termostat för radiator.")
    assert any("21 °C" in c["text"] for c in J.relevant_conditions(thermo, a["conditions"]))
    bl = {r["object"].lower(): r for r in J.boundary_list(a["boundaries"])}
    disk = bl["diskbänk och vattenlås"]
    assert disk["levereras_av"] == "Byggentreprenör" and disk["sources"][0]["ama"] == "PUB.4"
    assert bl["diskbänk"]["ansluts_av"] == "Denna entreprenör"
    assert bl["vattenmätare"]["levereras_av"] == "Kommunen" and bl["golvvärme i entré"]["ingår_ej"]
    assert a["options"] and "PUB.9" in a["option_codes"]


def test_the_offer_shows_options_apart_and_the_inquiry_carries_the_text():
    book = {"1": {"a": "1", "n": "WC", "p": 1000.0, "k": "1"}}
    base = {**_it(match={"status": "hittad", "hits": [{"ref": "1"}]}, rsk=["1"]), "option": False}
    opt = {**base, "id": "p2", "option": True}
    rows = OF.build_rows([J.quantity(base, None), J.quantity(opt, None)], book, None, {})
    t = OF.totals(rows)
    assert t["material"] == 10000.0 and t["optioner"]["material"] == 10000.0 and t["rader"] == 2
    d = drafts_by_maker([{**_it(code="KVP01", quantity_text="Enl ritn"), "inquiry_text": "PPC.61 Pumpar\nFrekvensstyrda, PN10."}])[0]
    assert "Frekvensstyrda, PN10." in d["text"] and "Frekvensstyrda, PN10." in d["html"]


def test_an_ab04_project_reads_its_description_with_analysis(tmp_path):
    import io
    import os
    import sys
    import openpyxl
    import pymupdf
    os.environ["VVS_DATABASE_URL"] = f"sqlite:///{tmp_path}/t.db"
    os.environ["VVS_STORAGE_ROOT"] = str(tmp_path / "st")
    os.environ["VVS_SECRET_KEY"] = "test"
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))
    sys.path.insert(0, os.path.dirname(__file__))
    for m in list(sys.modules):
        if m.startswith("app"):
            del sys.modules[m]
    from fastapi.testclient import TestClient
    from app.main import app
    from test_a_technical_description_is_read_to_its_materials import PAGES, _page
    with TestClient(app) as c:
        H = {"Authorization": "Bearer " + c.post("/api/auth/register", json={"email": "ab04@dahl.se", "password": "hemligt1"}).json()["access_token"]}
        p = c.post("/api/projects", json={"name": "AB04-projekt", "contract_form": "AB04"}, headers=H).json()
        doc = pymupdf.open()
        for i, rows in enumerate(PAGES):
            _page(doc, rows, i + 1, len(PAGES))
        s = c.post(f"/api/projects/{p['id']}/tech-specs", files={"file": ("tb.pdf", doc.tobytes(), "application/pdf")}, headers=H)
        assert s.status_code == 200 and s.json()["status"] == "COMPLETED"          # AB 04 tar emot beskrivningen
        got = c.get(f"/api/tech-specs/{s.json()['id']}", headers=H).json()
        it = got["items"][0]
        assert {"quantity_source", "quantity_trace", "option", "article_status", "inquiry_text"} <= set(it)
        a = c.get(f"/api/tech-specs/{s.json()['id']}/analysis", headers=H).json()
        assert {"contract", "conditions", "boundaries", "options", "quantity_priority"} <= set(a) and a["quantity_priority"] == "flagga"
        assert c.post(f"/api/projects/{p['id']}/quantity-priority", json={"priority": "ritning"}, headers=H).json() == {"quantity_priority": "ritning"}
        assert c.post(f"/api/projects/{p['id']}/quantity-priority", json={"priority": "x"}, headers=H).status_code == 422
        x = c.get(f"/api/tech-specs/{s.json()['id']}/boundaries.xlsx", headers=H)
        assert {"Gränsdragning", "Förutsättningar", "Optioner"} == set(openpyxl.load_workbook(io.BytesIO(x.content)).sheetnames)
