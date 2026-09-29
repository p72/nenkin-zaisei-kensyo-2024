# -*- coding: utf-8 -*-
"""玩具ケース（計画 §H「玩具ケース（検証の代わり）」）— 手計算できる最小の例で均衡の解法を見る
=================================================================================================
構造を変えた設定に正解（移植版）は無いので、式の目視と数値の一致をここに残す。

台帳は 1 制度・5 年度（添字 0〜4。0 が基準年度）。単位は「円」を 1 と読む。

    積立金[0] = 100、支出 X = 60 一定、国庫 K = 10 一定、妻積 T = 0、利回り ri = 0.02、
    年度内の収支に掛かる利回り ri2 = 0.01、物価 ci = 0.01、総報酬 = 500 一定
"""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from conftest import FAST                                     # noqa: E402,F401

from kosoku.axis import YEARS, AGES                           # noqa: E402
from kosoku.balance import (fixed_benefit_Sh, margin_fund_ratio, margin_stationary,   # noqa: E402
                            solve_premium, solve_payg, rule_of, RULES)
from kosoku.stages.s5_emp_shushi.shushi import C, NCOL         # noqa: E402


class _E:
    def __init__(self, n, ri=0.02, ri2=0.01, ci=0.01):
        self.ri = np.full(n, ri); self.ri2 = np.full(n, ri2); self.ci = np.full(n, ci)


def _ledger(n=5, fund0=100., X=60., K=10., wages=500.):
    Cc = np.zeros((1, NCOL, n))
    Cc[0, C.TUMITATE, 0] = fund0
    Cc[0, C.SHISHUTU, 1:] = X
    Cc[0, C.KOKKO, 1:] = K
    Cc[0, C.SOHOSHU, 1:] = wages
    return Cc


def test_賦課方式の手計算():
    """1 年度目: F=100, φ=ci=0.01, ri=0.02, ri2=0.01, K=10, T=0, X=60。
    P = [F(φ − ri) − (K + T − X)(1 + ri2)] / (1 + ri2) = [100 × (−0.01) − (−50)(1.01)] / 1.01
      = (−1 + 50.5) / 1.01 = 49.0099…
    運用 = F ri + (P + K − X + T) ri2 = 2 + (49.0099 + 10 − 60) × 0.01 = 2 − 0.009901 = 1.990099
    収入 = P + 運用 + K = 61.0、収支差 = 1.0 = F φ、積立金[1] = 101（物価で実質一定）。料率 = P / 500"""
    Cc = _ledger()
    E = _E(5)
    rates = solve_payg(Cc, C, E, 0, 1, 4, E.ci)
    P1 = (100. * (0.01 - 0.02) - (10. - 60.) * 1.01) / 1.01
    assert np.isclose(Cc[0, C.HOKENRYO, 1], P1)
    assert np.isclose(Cc[0, C.UNYO, 1], 2. + (P1 + 10. - 60.) * 0.01)
    assert np.isclose(Cc[0, C.SHUSHISA, 1], 1.0)
    assert np.isclose(Cc[0, C.TUMITATE, 1], 101.)
    assert np.isclose(rates[0, 1], P1 / 500.)
    # 毎年度、積立金は物価で実質一定
    for i in range(1, 5):
        assert np.isclose(Cc[0, C.TUMITATE, i], 100. * 1.01 ** i)
        assert np.isclose(Cc[0, C.SHUSHISA, i], Cc[0, C.TUMITATE, i - 1] * 0.01)
        assert np.isclose(Cc[0, C.SHUNYU, i], Cc[0, C.HOKENRYO, i] + Cc[0, C.UNYO, i] + Cc[0, C.KOKKO, i])


def test_料率の割線法_一次の問題は_2_回で解ける():
    """f(r) = 500 × r − 75（料率 r の保険料 500r と、支出側 75 の差）。解 r = 0.15。"""
    state = {"r": None}

    def apply_rate(r):
        state["r"] = r

    def evaluate():
        return 500. * state["r"] - 75.

    r, f, n, ok = solve_premium(apply_rate, evaluate, 0.10, 0.20, tol=1e-9)
    assert ok and abs(r - 0.15) < 1e-9 and abs(f) < 1e-9
    assert n <= 3


def test_料率の割線法_符号の変わる区間を自分で探す():
    """初期の 2 点が両方とも f < 0（料率が低すぎる）なら、0.05 ずつ上げて区間を作ってから詰める。
    f(r) = 500 r − 200 → r = 0.4。"""
    st = {}
    r, f, n, ok = solve_premium(lambda r: st.__setitem__("r", r), lambda: 500. * st["r"] - 200., 0.10, 0.12, 1e-9)
    assert ok and abs(r - 0.4) < 1e-9


def test_合わせる条件():
    Cc = _ledger()
    Cc[0, C.TUMITATE, 3] = 70.; Cc[0, C.SHISHUTU, 4] = 60.
    assert margin_fund_ratio(Cc, C, 4, 1.0) == 10.            # 積立金[3] − 支出[4] × 1
    Cc[0, C.SHUSHISA, 4] = 3.; Cc[0, C.TUMITATE, 3] = 100.
    assert np.isclose(margin_stationary(Cc, C, 4, 0.02), 1.)  # 収支差 3 − 100 × 0.02


def test_給付固定の累積調整率():
    """実績年度までは毎年の率で割り、あとはコホートでずらすだけ。"""
    x63 = AGES.i(63)
    rh = np.ones((YEARS.n, AGES.n))
    kijun, k_jis, ie = YEARS.i(2022), YEARS.i(2024), YEARS.i(2030)
    rh[YEARS.i(2023), x63:] = 1.01
    rh[YEARS.i(2024), x63:] = 1.02
    rh[YEARS.i(2025), x63:] = 1.05                             # 使われない（実績年度の後）
    Sh = fixed_benefit_Sh(rh, kijun, k_jis, ie, x63)
    assert np.isclose(Sh[YEARS.i(2024), x63], 1. / 1.01 / 1.02)
    assert np.isclose(Sh[YEARS.i(2030), x63 + 6], Sh[YEARS.i(2024), x63])   # 同じコホートで据え置き
    assert np.isclose(Sh[YEARS.i(2030), x63], Sh[YEARS.i(2024), x63])       # 63 歳は据え置き


def test_rule_of_と名前():
    class P:
        def __init__(self, d): self.d = d
        def get(self, k, default=None): return self.d.get(k, default)
    for name, (lever, target) in RULES.items():
        r = rule_of(P({"shushi.balance": {"rule": name}}))
        assert (r.lever, r.target) == (lever, target)
        assert r.benefit_fixed == (lever == "premium_rate")
    assert rule_of(P({})).name == "current"
    with pytest.raises(ValueError):
        rule_of(P({"shushi.balance": {"rule": "magic"}}))
