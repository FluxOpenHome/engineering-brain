import io

from eb.jobs import run_pending_once
from eb.specs.rules import check_requirement, check_text, classify_ears


def _rules(text: str) -> set[str]:
    return {i["rule"] for i in check_requirement(text)["issues"]}


def test_rules_catch_weak_modal_and_vague_terms():
    r = check_requirement("The pump should be adequate for the duty.")
    rules = {i["rule"]: i for i in r["issues"]}
    assert "R3-UseShall" in rules and rules["R3-UseShall"]["severity"] == "error"
    assert "should" in rules["R3-UseShall"]["message"]
    assert "R1-NoVagueTerms" in rules and "adequate" in rules["R1-NoVagueTerms"]["message"]


def test_rules_on_well_formed_requirements_are_quiet():
    assert _rules("The design pressure of the pump casing shall be not less than 16 bar(g).") == set()
    assert _rules("The pump shall deliver a rated flow of 250 m3/h at a differential head of 45 m.") == set()
    assert _rules("Casing material shall be ASTM A216 WCB carbon steel.") == set()


def test_rules_catch_structure_problems():
    assert "R2-NoEscapeClauses" in _rules("The valve shall close within 5 s where practicable.")
    assert "R4-SingleThought" in _rules("The pump shall start and the valve shall open.")
    assert "R4-SingleThought" in _rules("The unit shall log and/or alarm the event.")
    assert "R5-ActiveVoice" in _rules("The pump shall be delivered within 12 weeks.")
    assert "R5-ActiveVoice" not in _rules("The supplier shall deliver the pump within 12 weeks.")
    assert "R6-AvoidNegatives" in _rules("The pump shall not run dry.")
    assert "R7-UnitsOnNumbers" in _rules("The motor shall be rated for 400.")
    assert "R7-UnitsOnNumbers" not in _rules("The test shall follow ISO 9906 Grade 2B.")
    assert "R8-Tolerance" in _rules("The casing thickness shall be 12 mm.")
    assert "R8-Tolerance" not in _rules("The casing thickness shall be not less than 12 mm.")
    assert "R9-NoPronouns" in _rules("The pump shall start when it receives the signal.")
    assert "R10-Measurable" in _rules("The pump shall be quiet.")
    assert "R11-NoTBD" in _rules("The flange rating shall be TBD.")
    assert "R12-UniversalQuantifiers" in _rules("The system shall always log all events.")
    long = "The pump shall " + " ".join(["operate"] * 55) + "."
    assert "R13-Length" in _rules(long)


def test_ears_classification():
    assert (
        classify_ears("When the level exceeds 90%, the system shall close the inlet valve.") == "event-driven"
    )
    assert (
        check_requirement("When the level exceeds 90%, the system shall close the inlet valve.")[
            "ears_pattern"
        ]
        == "event-driven"
    )
    assert classify_ears("The pump shall deliver 250 m3/h.") == "ubiquitous"
    assert (
        classify_ears("While the pump is running, the controller shall monitor vibration.") == "state-driven"
    )
    assert classify_ears("Where a VSD is fitted, the motor shall be inverter-duty rated.") == "optional"
    assert (
        classify_ears("If the suction pressure falls below 1 bar(g), then the pump shall stop.") == "unwanted"
    )
    assert (
        classify_ears("While in standby, when the start signal is received, the pump shall start.")
        == "complex"
    )
    assert classify_ears("Centrifugal pumps for cooling water.") is None


def test_check_text_splits_and_summarises():
    text = (
        "## 4 Design\n\n4.1 The pump shall deliver 250 m3/h.\n"
        "The casing should be adequate. Painting is described in Annex A.\n"
    )
    out = check_text(text)
    assert [r["text"][:20] for r in out] == ["The pump shall deliv", "The casing should be"]
    assert out[0]["ears_pattern"] == "ubiquitous"
    assert {i["rule"] for i in out[1]["issues"]} >= {"R1-NoVagueTerms", "R3-UseShall"}


def test_templates_endpoint(client):
    r = client.get("/specs/templates")
    assert r.status_code == 200
    keys = {t["key"] for t in r.json()}
    assert keys >= {
        "centrifugal_pump",
        "control_valve",
        "power_transformer",
        "lv_switchgear",
        "pressure_vessel",
        "piping_system",
        "structural_steel",
        "hvac_ahu",
    }
    pump = next(t for t in r.json() if t["key"] == "centrifugal_pump")
    assert pump["discipline"] == "fluid" and pump["standards_refs"]
    electrical = [p for p in pump["parameters"] if p["interface"] == "electrical"]
    assert any(p["name"] == "Motor rated power" and p["unit"] == "kW" for p in electrical)
    assert any(p["interface"] == "structural" for p in pump["parameters"])
    assert pump["interface_checklist"] and {"topic", "from_discipline", "to_discipline", "check"} <= set(
        pump["interface_checklist"][0]
    )


def test_check_endpoint(client):
    r = client.post(
        "/specs/check",
        json={
            "text": "The pump should be adequate for the duty.\n"
            "When the level exceeds 90%, the system shall close the inlet valve."
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["requirements"]) == 2
    assert body["requirements"][1]["ears_pattern"] == "event-driven"
    assert body["summary"]["errors"] >= 2 and "warnings" in body["summary"]


def test_draft_endpoint_with_scripted_llm(client, sample_spec, fake_llm):
    r = client.post(
        "/documents",
        files={"file": ("ps-100.md", io.BytesIO(sample_spec.encode()), "text/markdown")},
        data={"doc_number": "PS-100", "revision": "A", "doc_type": "spec", "project": "CW-1"},
    )
    assert r.status_code == 201
    run_pending_once()

    fake_llm.parsed.append(
        {
            "parameters": [
                {
                    "name": "Rated flow",
                    "value": "250",
                    "unit": "m3/h",
                    "source_index": 0,
                    "note": "PS-100 4.1",
                },
                {"name": "Differential head", "value": "45", "unit": "m", "source_index": 0, "note": ""},
                {
                    "name": "Design pressure",
                    "value": "16",
                    "unit": "bar(g)",
                    "source_index": None,
                    "note": "",
                },
            ],
            "requirements_markdown": (
                "The pump shall deliver a rated flow of not less than 250 m3/h.\n"
                "The pump should have adequate head.\n"
            ),
        }
    )
    r = client.post(
        "/specs/draft",
        json={"template_key": "centrifugal_pump", "project": "CW-1", "context": "cooling water pump"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["markdown"].startswith("# Centrifugal pump requirement specification")
    assert "| Rated flow | 250 | m3/h | PS-100" in body["markdown"]
    assert "## 5 Interface requirements" in body["markdown"] and "motor rated power" in body["markdown"]
    params = {p["name"]: p for p in body["parameters"]}
    assert params["Rated flow"]["value"] == "250" and params["Rated flow"]["source"].startswith("PS-100")
    assert params["Design pressure"]["value"] == "16" and params["Design pressure"]["source"] is None
    assert params["Dry mass"]["value"] is None and params["Dry mass"]["interface"] == "structural"
    issues = {i["text"]: i for i in body["issues"]}
    bad = issues["The pump should have adequate head."]
    assert {x["rule"] for x in bad["issues"]} >= {"R1-NoVagueTerms", "R3-UseShall"}
    assert body["issue_summary"]["errors"] >= 2
    # The LLM saw the template and the evidence as documents.
    call = fake_llm.calls[-1]
    assert call["documents"] and "Rated flow" in call["user"]

    assert client.post("/specs/draft", json={"template_key": "nope"}).status_code == 404
