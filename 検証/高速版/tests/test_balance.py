# -*- coding: utf-8 -*-
"""均衡の解法（`kosoku/balance.py`、フェーズ H）を⑤で回す — 港の入力（ケース 3001）
====================================================================================
構造を変えた設定に正解は無いので見るのは 3 つ: (1) 既定 `current` は移植版の答え（最終所得代替率
56.9122495807、終了年度 2024／2039）のまま、(2) 各解法が自分の条件を満たす（有限均衡・毎年均衡・定常）、
(3) 恒等式（収入計 = 部分和、積立金の漸化式）。`work/suuri/rev2024` が無ければ飛ばす。
玩具ケースは `tests/toy/test_balance_toy.py`。
"""
import os
import sys

import numpy as np
import pytest

from conftest import FAST
sys.path.insert(0, os.path.normpath(os.path.join(FAST, "..")))
import suuri_env                                            # noqa: E402

from kosoku.axis import YEARS                                # noqa: E402
from kosoku.policy import load_policy                        # noqa: E402
from kosoku.indicators import indicators                     # noqa: E402
from kosoku.stages.s5_emp_shushi import run as R             # noqa: E402
from kosoku.stages.s5_emp_shushi.shushi import C             # noqa: E402

CASE = "3001"
S = suuri_env.suuri
PORT_FINAL = 56.9122495807026                                # 移植版（原本 C）のケース 3001


def _need(path):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        pytest.skip("無い: %s" % path)
    return path


@pytest.fixture(scope="module")
def inputs():
    pol = load_policy()
    return R.read_inputs(pol, CASE, _need(S("emp")), _need(S("bas")), _need(S("nat")),
                         _need(S("wakuc", "rslt", "ver_4_1", "rslt" + CASE)),
                         _need(S("emp", "data", "u-rev", "econ", "econ-%s.csv" % CASE)))


def _run(inputs, *overlay):
    inputs.pol = load_policy(*overlay)
    return R.run(inputs, CASE)


def _identities(Cc, i1, ie):
    for i in range(i1, ie + 1):
        assert np.allclose(Cc[:, C.SHUNYU, i], Cc[:, C.HOKENRYO, i] + Cc[:, C.UNYO, i] + Cc[:, C.KOKKO, i]
                           + Cc[:, C.SHIEN_IN, i] + Cc[:, C.NOFUKIN, i] + Cc[:, C.TUMATUMI, i], rtol=1e-9)
        assert np.allclose(Cc[:, C.SHUSHISA, i], Cc[:, C.SHUNYU, i] - Cc[:, C.SHISHUTU, i], rtol=1e-9)
        assert np.allclose(Cc[:, C.TUMITATE, i], Cc[:, C.TUMITATE, i - 1] + Cc[:, C.SHUSHISA, i], rtol=1e-9)


def test_既定は移植版のまま(inputs):
    r = _run(inputs)
    assert r.sol.rule == "current"
    assert abs(r.out.final_rate["total"] - PORT_FINAL) < 1e-9
    assert (r.out.owari["kend_h"], r.out.owari["kend_t"]) == (2024, 2039)
    ind = indicators(r)
    assert abs(ind["premium_rate"][2030] - 0.183) < 1e-12               # 上限 18.3% に張り付く
    assert 0.05 < ind["benefit_to_gdp"][2024] < 0.15                    # 厚年 4 制度の支出 ÷ GDP（2024 年度は約 9%）
    assert ind["fund_ratio"][2025] > 3.


def test_給付固定_料率均衡(inputs):
    """2027 年度から一定の率で 2120 年度の積立度合 = 1。ケース 3001 は厚年の調整が 2024 年度で終わり
    積立金が余るので、率は 18.3% より低くなる。"""
    r = _run(inputs, "balance_premium")
    sol = r.sol
    assert sol.rule == "premium" and sol.ok and sol.premium_rate is not None
    assert 0.10 < sol.premium_rate < 0.183
    tot = r.Cc.sum(0)
    kend = YEARS.i(2120)
    assert abs(tot[C.TUMITATE, kend - 1] / tot[C.SHISHUTU, kend] - 1.) < 1e-6
    ind = indicators(r)
    assert abs(ind["premium_rate"][2040] - sol.premium_rate) < 1e-3     # 第3種の上乗せ分だけずれる
    assert abs(ind["premium_rate"][2026] - 0.183) < 1e-3                # 前は現行のまま（実効料率は第3種のぶんだけずれる）
    assert r.out.final_rate["hirei"] == pytest.approx(24.9711420191125, abs=1e-6)  # 給付は動かない
    _identities(r.Cc, YEARS.i(2023), YEARS.i(2125))


def test_賦課方式(inputs):
    """2027 年度から毎年 収支差 = 積立金 × 物価上昇率（実質一定）。"""
    r = _run(inputs, "balance_payg")
    assert r.sol.rule == "payg" and r.sol.rates is not None
    tot = r.Cc.sum(0)
    for y in range(2027, 2126):
        i = YEARS.i(y)
        assert np.isclose(tot[C.SHUSHISA, i], tot[C.TUMITATE, i - 1] * r.E.ci[i], rtol=1e-8)
    ind = indicators(r)
    assert 0.10 < ind["premium_rate"][2027] < 0.20
    assert ind["premium_rate"][2125] > ind["premium_rate"][2027]        # 高齢化で上がる
    assert set(ind["payg_rates"]) == {"kou", "kok", "ren", "sig"}
    _identities(r.Cc, YEARS.i(2023), YEARS.i(2125))


def test_永久均衡_料率(inputs):
    """終期で 収支差 = 積立金 × g（g = 終期の名目賃金上昇率）。"""
    r = _run(inputs, "balance_perpetual_premium")
    sol = r.sol
    assert sol.rule == "perpetual_premium" and sol.ok
    tot = r.Cc.sum(0)
    ie = YEARS.i(2125)
    assert np.isclose(tot[C.SHUSHISA, ie], tot[C.TUMITATE, ie - 1] * r.E.h[ie], rtol=1e-8)
    _identities(r.Cc, YEARS.i(2023), YEARS.i(2125))


def test_永久均衡_給付水準(inputs):
    """給付水準を動かす永久均衡。ケース 3001 は 2024 年度で条件が満たされる（余剰）ので調整なし。"""
    r = _run(inputs, "balance_perpetual")
    assert r.sol.rule == "perpetual"
    tot = r.Cc.sum(0)
    ie = YEARS.i(2125)
    assert tot[C.SHUSHISA, ie] >= tot[C.TUMITATE, ie - 1] * r.E.h[ie]   # 条件の余裕 ≥ 0
    assert r.out.owari["kend_h"] == 2024
    _identities(r.Cc, YEARS.i(2023), YEARS.i(2125))
