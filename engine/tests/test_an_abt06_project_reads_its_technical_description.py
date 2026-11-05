"""Ett ABT 06-projekt med teknisk beskrivning: uppladdning, poster, matchning, mejlutkast och export.

Kryssrutan "Teknisk beskrivning" hör till ABT 06. Ett AB 04-projekt kan inte få den, ett ABT 06-projekt kan få den
när det skapas eller i efterhand, och den följer med projektet ut i listan.
"""
from __future__ import annotations

import os
import sys

import pymupdf
import pytest

sys.path.insert(0, os.path.dirname(__file__))
from test_a_technical_description_is_read_to_its_materials import PAGES, _page  # noqa: E402


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("tb")
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


@pytest.fixture(scope="module")
def pdf():
    doc = pymupdf.open()
    for i, rows in enumerate(PAGES):
        _page(doc, rows, i + 1, len(PAGES))
    data = doc.tobytes()
    doc.close()
    return data


def _login(client, email):
    r = client.post("/api/auth/register", json={"email": email, "password": "hemligt1"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_the_whole_flow(client, pdf):
    admin = _login(client, "admin@example.com")          # den första användaren är administratör
    H = _login(client, "kalkyl@example.com")

    ab04 = client.post("/api/projects", json={"name": "AB", "contract_form": "AB04", "tech_spec": True}, headers=H).json()
    assert ab04["tech_spec"] is False                     # teknisk beskrivning hör till ABT 06
    p = client.post("/api/projects", json={"name": "Tvätthall", "contract_form": "ABT06", "tech_spec": True},
                    headers=H).json()
    assert p["tech_spec"] is True and p["contract_form"] == "ABT06"
    assert client.patch(f"/api/projects/{ab04['id']}/form", json={"tech_spec": True}, headers=H).status_code == 422

    up = client.post(f"/api/projects/{p['id']}/tech-specs", files={"file": ("tb.pdf", pdf, "application/pdf")}, headers=H)
    assert up.status_code == 200, up.text
    s = up.json()
    assert s["status"] == "COMPLETED" and s["n_pages"] == 3 and s["stats"]["posts"] >= 8 and not s["duplicate"]
    again = client.post(f"/api/projects/{p['id']}/tech-specs", files={"file": ("igen.pdf", pdf, "application/pdf")},
                        headers=H).json()
    assert again["duplicate"] and again["id"] == s["id"]

    got = client.get(f"/api/tech-specs/{s['id']}", headers=H).json()
    items = {it["code"] + "/" + it["kind"]: it for it in got["items"] if it["code"]}
    b202 = items["B202B/post"]
    assert b202["category"] == "Golvbrunnar" and b202["manufacturer"] == "Furhoff"
    assert b202["match"]["status"] in ("hittad", "möjlig", "saknas")
    cats = {c["value"] for c in got["facets"]["categories"]}
    assert "Golvbrunnar" in cats and "Tvättställ" in cats
    assert {m["value"] for m in got["facets"]["manufacturers"]} >= {"Furhoff", "Purus", "IFÖ", "FMM", "Broen"}
    assert got["sources"]["katalog"]["n"] > 20000         # Dahls produktkatalog ligger med tjänsten

    ts = items["TS101/post"]
    assert ts["match"]["status"] == "hittad" and ts["match"]["hits"][0]["ref"] == "7606418"

    mail = client.post(f"/api/tech-specs/{s['id']}/mail", json={"ids": [b202["id"]], "to": "inkop@example.com"},
                       headers=H).json()
    d0 = mail["drafts"][0]
    assert mail["n"] == 1 and d0["maker"] == "Furhoff" and "B202B" in d0["text"] and d0["subject"].startswith("Prisförfrågan")
    assert d0["mailto"].startswith("mailto:") and "<table" in d0["html"] and "X-Unsent: 1" in d0["eml"]

    csv = client.get(f"/api/tech-specs/{s['id']}/items.csv", headers=H)
    assert csv.status_code == 200 and "B202B" in csv.text and "Golvbrunnar" in csv.text

    other = _login(client, "annan@example.com")
    assert client.get(f"/api/tech-specs/{s['id']}", headers=other).status_code == 404

    # katalogen: bara administratören läser in den, och en uppladdad katalog gäller genast
    assert client.post("/api/catalog/upload", files={"file": ("k.pdf", pdf, "application/pdf")}, headers=H).status_code == 403
    cat = pymupdf.open()
    pg = cat.new_page()
    pg.insert_text((50, 80), "Furhoff Furo 142 golvbrunn 273x273 110 epoxi", fontname="helv", fontsize=10)
    r = client.post("/api/catalog/upload", files={"file": ("dahl.pdf", cat.tobytes(), "application/pdf")}, headers=admin)
    assert r.status_code == 200, r.text
    assert r.json()["pages"] == 1
    st = client.get("/api/catalog", headers=H).json()
    assert st["katalog"]["pages"] == 1
    after = client.get(f"/api/tech-specs/{s['id']}", headers=H).json()
    b = next(it for it in after["items"] if it["code"] == "B202B")
    assert b["match"]["in_catalog"]

    assert client.delete(f"/api/tech-specs/{s['id']}", headers=H).json()["ok"]
    assert client.get(f"/api/projects/{p['id']}/tech-specs", headers=H).json() == []


def test_abt06_comes_in_two_variants(client):
    """Med ritningar (handlingens blad, med eller utan beskrivning) eller med bara den tekniska beskrivningen."""
    H = _login(client, "varianter@example.com")
    ritn = client.post("/api/projects", json={"name": "R", "contract_form": "ABT06"}, headers=H).json()
    assert ritn["abt_variant"] == "ritningar" and ritn["tech_spec"] is False
    only = client.post("/api/projects", json={"name": "B", "contract_form": "ABT06", "abt_variant": "beskrivning"},
                       headers=H).json()
    assert only["abt_variant"] == "beskrivning" and only["tech_spec"] is True   # bara beskrivningen: den finns alltid
    ab = client.post("/api/projects", json={"name": "A", "contract_form": "AB04", "abt_variant": "beskrivning"}, headers=H).json()
    assert ab["abt_variant"] == "" and ab["tech_spec"] is False
    changed = client.patch(f"/api/projects/{ritn['id']}/form", json={"abt_variant": "beskrivning"}, headers=H).json()
    assert changed["abt_variant"] == "beskrivning" and changed["tech_spec"] is True
    assert client.patch(f"/api/projects/{ritn['id']}/form", json={"abt_variant": "x"}, headers=H).status_code == 422
    assert {p["abt_variant"] for p in client.get("/api/projects", headers=H).json()} == {"beskrivning", ""}


def test_a_file_that_is_not_a_pdf_is_refused(client):
    H = _login(client, "tredje@example.com")
    p = client.post("/api/projects", json={"name": "X", "contract_form": "ABT06", "tech_spec": True}, headers=H).json()
    r = client.post(f"/api/projects/{p['id']}/tech-specs", files={"file": ("tb.pdf", b"hej", "application/pdf")}, headers=H)
    assert r.status_code == 400
