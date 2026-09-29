# -*- coding: utf-8 -*-
"""フェーズ F: レバー（オプション試算）。overlay の読み込み、`Options` の意味（据え置き・名前）、
基礎45年化の加入可能年数の表（港の `set_kflcan` の値と照合）。

段階をまたぐ数値の検証（原本 C のレバー実行との比較）は README「フェーズ F の結果」。ここは
速いテストだけ。"""
import pytest

from kosoku.axis import YEARS, ALL_COHORTS
from kosoku.policy import load_policy
from kosoku.options import Options, options_of, NAMES
from kosoku.pipeline import base_policy
from kosoku.stages.s2_emp_kyufu.seid import kflcan_table

# overlay の名前 → 立つレバー（それ以外は既定）
OVERLAYS = {
    "kakudai_1": dict(kakudai=1), "kakudai_2": dict(kakudai=2), "kakudai_3": dict(kakudai=3),
    "kakudai_4": dict(kakudai=4), "kakudai_5": dict(kakudai=5),
    "sigo": dict(sigo=1), "kozax": dict(kozax=1),
    "houjou_1": dict(houjou=1), "houjou_2": dict(houjou=2), "houjou_3": dict(houjou=3),
    "tougou": dict(tougou=1), "dmacro": dict(dmacro=1), "nocarry": dict(carry=0),
}


def test_既定は通常試算():
    o = options_of(load_policy())
    assert o == Options()
    assert o.tag == "base" and not o.freeze_kiso


@pytest.mark.parametrize("name", sorted(OVERLAYS))
def test_overlay_で_1_つずつ立つ(name):
    o = options_of(load_policy(name))
    assert o == Options(**OVERLAYS[name]), name


def test_overlay_は重ねられる():
    o = options_of(load_policy("kozax", "nocarry"))
    assert o == Options(kozax=1, carry=0)
    assert o.tag == "kozax+nocarry"
    assert not o.freeze_kiso                       # キャリーオーバー廃止が立つと③④も動く


def test_freeze_kiso_は高在老と報酬上限だけ():
    assert Options(kozax=1).freeze_kiso
    assert Options(houjou=3).freeze_kiso
    assert Options(kozax=1, houjou=1).freeze_kiso
    for kw in (dict(kakudai=1), dict(sigo=1), dict(tougou=1), dict(dmacro=1), dict(carry=0)):
        assert not Options(kozax=1, **kw).freeze_kiso, kw
        assert not Options(**kw).freeze_kiso, kw


def test_tag():
    assert Options(kakudai=3).tag == "kakudai3"
    assert Options(houjou=2, tougou=1).tag == "houjou2+tougou"
    assert Options(sigo=1, dmacro=1, carry=0).tag == "sigo+dmacro+nocarry"


def test_範囲外は止める():
    pol = load_policy()
    data = dict(pol.data); data["options"] = dict(pol.data["options"], houjou=4)
    bad = type(pol)(data=data, sources=pol.sources, origin=pol.origin)
    with pytest.raises(ValueError):
        options_of(bad)
    assert set(pol.data["options"]) == set(NAMES)


def test_base_policy_はレバーだけ戻す():
    pol = load_policy("houjou_3", "tougou")
    base = base_policy(pol)
    assert options_of(base) == Options()
    assert base.get("kounen.years.houjouyr") == pol.get("kounen.years.houjouyr")
    assert base.get("kounen.houjou.r98") == pol.get("kounen.houjou.r98")
    assert options_of(pol) == Options(houjou=3, tougou=1)      # 元は変えない


# 港 `emp_kyufu/cntl.py:set_kflcan` を flg_sigo=1 で回した値（年度, 生年度 → 加入可能年数）。
# canyr=2031: 年度の上限は 2031 から 41、3 年ごとに +1 で 2043 から 45。生年度の上限は 1971 年度生から
# 41、2 年ごとに +1 で 1979 年度生から 45。両方の min。それ以外（2031 年度前、1971 年度生前）は 40
_PORT_KFLCAN = {
    (2025, 1970): 40, (2027, 1968): 40, (2030, 1971): 40, (2031, 1970): 40, (2125, 1926): 40, (2040, 1966): 40,
    (2031, 1971): 41, (2031, 1979): 41, (2043, 1971): 41, (2125, 1971): 41, (2033, 1975): 41,
    (2034, 1973): 42, (2036, 1980): 42,
    (2037, 1975): 43, (2039, 1985): 43, (2040, 1976): 43,
    (2040, 1977): 44,
    (2043, 1979): 45, (2046, 1990): 45, (2050, 2000): 45, (2125, 2125): 45,
}


def test_kflcan_table_は港の_set_kflcan_と同じ():
    T = kflcan_table(load_policy("sigo"))
    assert T.shape == (YEARS.n, ALL_COHORTS.n)
    for (y, c), v in _PORT_KFLCAN.items():
        assert T[YEARS.i(y), ALL_COHORTS.i(c)] == v, (y, c)
    assert (T[:YEARS.i(2031)] == 40).all()                      # canyr の前は全部 40
    assert (T[:, :ALL_COHORTS.i(1971)] == 40).all()             # canyr−60 年度生の前も 40
    assert T.min() == 40 and T.max() == 45


def test_kflcan_table_通常試算でも表は作れる():
    T = kflcan_table(load_policy())
    assert (T >= 40).all() and (T <= 45).all()
