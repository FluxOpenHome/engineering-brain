from eb.compliance.units import Quantity, compare, parse_quantity


def _one(text: str) -> Quantity:
    qs = parse_quantity(text)
    assert len(qs) == 1, (text, qs)
    return qs[0]


def test_parse_flow_and_head_in_one_clause():
    qs = parse_quantity("The pump shall deliver a rated flow of 250 m3/h at a differential head of 45 m.")
    assert [(q.value, q.unit) for q in qs] == [(250.0, "m**3/hour"), (45.0, "m")]
    assert "flow" in qs[0].context


def test_parse_gauge_suffix_is_a_flag_not_a_unit():
    for text in ("16 bar(g)", "16 barg", "16 bar (g)"):
        q = _one(text)
        assert q.unit == "bar" and q.gauge == "g", text
    assert _one("3 bara").gauge == "a"
    assert _one("20 psig").unit == "psi" and _one("20 psig").gauge == "g"


def test_parse_engineering_spellings():
    assert _one("250 m³/h").unit == "m**3/hour"
    assert _one("38 °C").unit == "degC" and _one("38 degC").unit == "degC"
    assert _one("400 V").unit == "V" and _one("50 Hz").unit == "Hz"
    assert _one("2950 rpm").unit == "revolutions_per_minute"
    assert _one("2.5 MPa").unit == "MPa" and _one("150 psi").unit == "psi" and _one("350 kPa").unit == "kPa"
    assert _one("75 kW").unit == "kW" and _one("12 mm").unit == "mm" and _one("1,500 kg").value == 1500.0
    assert _one("82.5%").unit == "percent" and _one("82.5%").percent is True
    assert _one("400V").value == 400.0  # glued unit


def test_parse_bare_decimal_and_identifiers():
    qs = parse_quantity(
        "Motor shall be rated for 400 V, 50 Hz, 3-phase supply with a service factor of 1.15."
    )
    assert [q.value for q in qs] == [400.0, 50.0, 1.15]
    assert qs[2].unit is None
    assert parse_quantity("Casing material shall be ASTM A216 WCB carbon steel.") == []
    assert parse_quantity("A performance test per ISO 9906 Grade 2B shall be witnessed.") == []
    assert parse_quantity("The pump shall be painted RAL 5015.") == []


def test_parse_ranges_ops_and_tolerances():
    r = _one("operating range 10–16 bar")
    assert (r.value, r.high, r.op) == (10.0, 16.0, "between")
    assert _one("≥ 16 bar").op == ">="
    assert _one("not less than 16 bar").op == ">="
    assert _one("shall not exceed 85 dB(A)").op == "<="
    assert _one("maximum 40 degC").op == "<="
    t = _one("45 m ±5%")
    assert t.tol_rel == 0.05 and t.unit == "m"
    t2 = _one("1200 +/- 2 mm")
    assert t2.value == 1200.0 and t2.unit == "mm" and t2.tol == 2.0


def test_compare_flow_pass():
    r = compare({"param": "rated flow", "op": ">=", "value": 200, "unit": "m3/h"}, _one("250 m3/h"))
    assert r["result"] == "pass"
    assert r["found_converted"]["value"] == 250.0


def test_compare_gauge_pressure_pass():
    r = compare({"param": "design pressure", "op": ">=", "value": 16, "unit": "bar"}, _one("20 bar(g)"))
    assert r["result"] == "pass"


def test_compare_dimensionless_fail():
    r = compare(
        {"param": "service factor", "op": ">=", "value": 1.15, "unit": None}, _one("service factor 1.0")
    )
    assert r["result"] == "fail"
    assert "1.15" in r["detail"]


def test_compare_head_fail():
    r = compare({"param": "head", "op": ">=", "value": 50, "unit": "m"}, _one("45 m"))
    assert r["result"] == "fail"


def test_compare_converts_kpa_bar_psi_and_flow_units():
    assert compare({"op": ">=", "value": 1600, "unit": "kPa"}, _one("16 bar"))["result"] == "pass"
    assert compare({"op": ">=", "value": 16, "unit": "bar"}, _one("1500 kPa"))["result"] == "fail"
    assert compare({"op": ">=", "value": 16, "unit": "bar"}, _one("300 psi"))["result"] == "pass"
    r = compare({"op": "==", "value": 250, "unit": "m3/h", "tol": "5%"}, _one("69 L/s"))
    assert r["result"] == "pass" and abs(r["found_converted"]["value"] - 248.4) < 0.01
    assert compare({"op": "==", "value": 250, "unit": "m3/h"}, _one("69 L/s"))["result"] == "fail"


def test_compare_unknown_unit_and_dimension_mismatch_never_pass():
    assert compare({"op": ">=", "value": 16, "unit": "widgets"}, _one("20 bar"))["result"] == "unknown"
    assert compare({"op": ">=", "value": 16, "unit": "bar"}, _one("20 m"))["result"] == "unknown"
    weird = Quantity(value=20.0, unit="widgets", unit_text="widgets", text="20 widgets")
    assert compare({"op": ">=", "value": 16, "unit": "bar"}, weird)["result"] == "unknown"
    assert (
        compare({"op": ">=", "value": 16, "unit": "bar"}, _one("service factor 1.0"))["result"] == "unknown"
    )
    assert compare({"op": "??", "value": 16, "unit": "bar"}, _one("20 bar"))["result"] == "unknown"


def test_compare_ops_between_and_absolute_vs_gauge():
    assert (
        compare({"op": "between", "value": 10, "high": 16, "unit": "bar"}, _one("12 bar"))["result"] == "pass"
    )
    assert (
        compare({"op": "between", "value": 10, "high": 16, "unit": "bar"}, _one("18 bar"))["result"] == "fail"
    )
    assert compare({"op": "<=", "value": 40, "unit": "degC"}, _one("100 degF"))["result"] == "pass"
    assert compare({"op": "<", "value": 40, "unit": "degC"}, _one("40 degC"))["result"] == "fail"
    # 17 bar(a) is 15.99 bar(g): below a 16 bar(g) requirement
    assert compare({"op": ">=", "value": 16, "unit": "bar(g)"}, _one("17 bar(a)"))["result"] == "fail"
    assert compare({"op": ">=", "value": 16, "unit": "bar(g)"}, _one("17.5 bar(a)"))["result"] == "pass"
    # a range must lie entirely on the right side of the bound
    assert compare({"op": ">=", "value": 16, "unit": "bar"}, _one("10–16 bar"))["result"] == "fail"
    assert compare({"op": "<=", "value": 16, "unit": "bar"}, _one("10–16 bar"))["result"] == "pass"
