# -*- coding: utf-8 -*-
"""policy の読み手: `{value, source}` の畳み込み、overlay の merge、未知キーは
エラー、Schedule と Rounding。"""
import os

import pytest
import yaml

from kosoku.policy.load import load_policy, fold
from kosoku.policy.model import Schedule, Rounding, Policy

BASE = {
    "kounen": {
        "hokenryoritu": {
            "cap": {"value": 0.183, "source": "emp_shushi/shus.py:110"},
            "step": 0.00354,
        },
        "shikyu_kaishi": {"by": "cohort", "points": {1957: 63, 1959: 64, 1961: 65}},
    },
    "kiso": {"mangaku_round": {"unit": 100, "mode": "nearest"}},
}


def _write(tmp_path, name, doc):
    p = tmp_path / name
    p.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    return str(p)


def test_foldと出典():
    src = {}
    data = fold(BASE, (), src)
    assert data["kounen"]["hokenryoritu"]["cap"] == 0.183
    assert src["kounen.hokenryoritu.cap"] == "emp_shushi/shus.py:110"
    # 構造のキー（表引きの by:）は値ではないので「(構造)」と印が付く
    assert src["kounen.shikyu_kaishi.by"] == "(構造)"
    assert set(src) == {"kounen.hokenryoritu.cap", "kounen.shikyu_kaishi.by"}


def test_load_と_get_と_unsourced(tmp_path):
    pol = load_policy(_write(tmp_path, "base.yaml", BASE))
    assert pol.get("kounen.hokenryoritu.cap") == 0.183
    assert pol.get("nai.key", None) is None
    with pytest.raises(KeyError):
        pol.get("nai.key")
    assert "kounen.hokenryoritu.step" in pol.unsourced()
    assert "kounen.hokenryoritu.cap" not in pol.unsourced()


def test_overlayはkey_pathでmerge(tmp_path):
    base = _write(tmp_path, "base.yaml", BASE)
    ov = _write(tmp_path, "kozax.yaml", {"kounen": {"hokenryoritu": {"cap": 0.20}}})
    pol = load_policy(base, ov)
    assert pol.get("kounen.hokenryoritu.cap") == 0.20
    assert pol.get("kounen.hokenryoritu.step") == 0.00354
    assert pol.origin == ("base.yaml", "kozax.yaml")


def test_overlayの未知キーは落ちる(tmp_path):
    base = _write(tmp_path, "base.yaml", BASE)
    ov = _write(tmp_path, "typo.yaml", {"kounen": {"hokenryoritsu": {"cap": 0.20}}})
    with pytest.raises(KeyError):
        load_policy(base, ov)


def test_schedule():
    s = Schedule.from_mapping("cohort", {1957: 63, 1959: 64, 1961: 65})
    assert s.at(1950) == 63 and s.at(1957) == 63 and s.at(1958) == 63
    assert s.at(1959) == 64 and s.at(1960) == 64 and s.at(1961) == 65 and s.at(1999) == 65
    assert list(s.array([1950, 1960, 1970])) == [63, 64, 65]
    with pytest.raises(ValueError):
        Schedule("year", ((2, 1), (1, 2)))


def test_policy_schedule_と_rounding(tmp_path):
    pol = load_policy(_write(tmp_path, "base.yaml", BASE))
    assert pol.schedule("kounen.shikyu_kaishi").at(1960) == 64
    r = pol.rounding("kiso.mangaku_round")
    assert r.apply(816049.9) == 816000. and r.apply(816050.) == 816100.
    assert Rounding(0.001).apply(1.0234) == pytest.approx(1.023)
    assert Rounding(10, "down").apply(17009.9) == 17000.


def test_既定は原本どおりで_fix_bugs_が癖だけを直す():
    """既定は原本の癖（J1・J2・J3・B11）どおり。`fix_bugs` はその 4 つだけを意図どおりにする。"""
    base = load_policy()
    fix = load_policy("fix_bugs")
    g0, g1 = base.get, fix.get
    assert g0("kounen.tables.tmq")[10] == 369 and g1("kounen.tables.tmq")[10] == 1369
    assert g0("kounen.siml.shke.ab_factor.ren") == 461.6518
    assert g1("kounen.siml.shke.ab_factor.ren") == 0.4616518
    for k in ("b11_izoku_lifetable_sex", "j3_waribiki_ninzu_2023"):
        assert g0("kokunen.quirks." + k) is True and g1("kokunen.quirks." + k) is False
    # それ以外の葉は変わらない
    changed = {"kounen.tables.tmq", "kounen.siml.shke.ab_factor.ren",
               "kokunen.quirks.b11_izoku_lifetable_sex", "kokunen.quirks.j3_waribiki_ninzu_2023"}

    def leaves(d, pre=()):
        for k, v in d.items():
            if isinstance(v, dict):
                yield from leaves(v, pre + (k,))
            else:
                yield ".".join(pre + (str(k),)), v
    a, b = dict(leaves(base.data)), dict(leaves(fix.data))
    assert set(a) == set(b)
    assert {k for k in a if a[k] != b[k]} == changed
