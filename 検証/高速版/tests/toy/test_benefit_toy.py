# -*- coding: utf-8 -*-
"""玩具ケース（計画 §J）— 拠出履歴・年金現価率・NDC・世代別倍率を手計算と合わせる
===================================================================================
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from conftest import FAST                                     # noqa: E402,F401

from kosoku.axis import YEARS, ALL_COHORTS                    # noqa: E402
from kosoku.history import by_cohort, contribution_history, History   # noqa: E402
from kosoku.benefit_formula import (annuity_divisor, cohort_survival, ndc, flat, minimum_guarantee,   # noqa: E402
                                    generational_ratio, initial_balance_from_old)


def test_by_cohort_は年度と年齢を生年度に散らす():
    a = np.zeros((YEARS.n, 3))
    a[YEARS.i(2030), 0] = 1.          # 2030 年度 20 歳 → 2010 年度生
    a[YEARS.i(2031), 1] = 2.          # 2031 年度 21 歳 → 2010 年度生
    a[YEARS.i(2031), 2] = 5.          # 2031 年度 22 歳 → 2009 年度生
    B = by_cohort(a, age_lo=20)
    assert B[ALL_COHORTS.i(2010), YEARS.i(2030)] == 1. and B[ALL_COHORTS.i(2010), YEARS.i(2031)] == 2.
    assert B[ALL_COHORTS.i(2009), YEARS.i(2031)] == 5. and B.sum() == 8.


def test_拠出履歴の手計算():
    """1 人が 2030 年度（20 歳）と 2031 年度（21 歳）に報酬 100（基準年度価格）で加入。賃金指数 ad は 2030 で 2、
    2031 で 4、料率 0.1。拠出 = 100×2×0.1 = 20、100×4×0.1 = 40。名目累積 60、賃金評価の累積（2031 時点）=
    20 × 4/2 + 40 = 80。"""
    l = np.zeros((YEARS.n, 3, 130)); bn = np.zeros((YEARS.n, 130, 4)); ad = np.zeros(YEARS.n); rate = np.full(YEARS.n, 0.1)
    l[YEARS.i(2030), 1, 20] = 1.; l[YEARS.i(2031), 1, 21] = 1.
    bn[:, :, 1] = 100.
    ad[YEARS.i(2030)] = 2.; ad[YEARS.i(2031)] = 4.; ad[YEARS.i(2032):] = 4.
    H = contribution_history(l, bn, ad, rate, 2030, sexes=(1,), ages=(15, 85))
    c = ALL_COHORTS.i(2010)
    assert H.contrib[c, YEARS.i(2030)] == 20. and H.contrib[c, YEARS.i(2031)] == 40.
    assert H.cum_nominal[c, YEARS.i(2031)] == 60.
    assert np.isclose(H.cum_indexed[c, YEARS.i(2031)], 80.)
    assert np.isclose(H.cum_indexed[c, YEARS.i(2040)], 80.)          # 指数が動かなければ残高も動かない
    assert H.insured[c, YEARS.i(2030)] == 1. and H.wages[c, YEARS.i(2031)] == 400.


def test_年金現価率の手計算():
    """l = [1, 1, 0.5, 0] を 65 歳から: (1+1)/2 + (1+0.5)/2 + (0.5+0)/2 = 1 + 0.75 + 0.25 = 2.0。"""
    surv = np.zeros(69); surv[:66] = 1.; surv[66] = 1.; surv[67] = 0.5; surv[68] = 0.
    assert np.isclose(annuity_divisor(surv, 65), 2.0)
    # 割引 > 指標化なら小さくなる: 1 + 0.75/1.1 + 0.25/1.21
    assert np.isclose(annuity_divisor(surv, 65, growth=0., discount=0.1), 1. + 0.75 / 1.1 + 0.25 / 1.21)


def test_生命表を生年で斜めに読む():
    qp = np.zeros((100, 130, 3))
    qp[YEARS.i(2030):, 70, 1] = 0.5                      # 2030 年度から 70 歳の死亡率 0.5
    l_old = cohort_survival(qp, 1959, 1)                 # 70 歳は 2029 年度 → 死なない
    l_new = cohort_survival(qp, 1960, 1)                 # 70 歳は 2030 年度 → 半分
    assert l_old[71] == 1. and np.isclose(l_new[71], 0.5)
    assert np.isclose(cohort_survival(qp, 2100, 1)[71], 0.5)   # 2070 年度より先は据え置き


def test_NDC_と移行と最低保障と定額():
    l = np.zeros((YEARS.n, 3, 130)); bn = np.zeros((YEARS.n, 130, 4)); ad = np.ones(YEARS.n); rate = np.full(YEARS.n, 0.2)
    birth = 1985
    for age in range(20, 65):                            # 20〜64 歳、年 100 の報酬、1 人
        l[YEARS.i(birth + age), 1, age] = 1.
    bn[:, :, 1] = 100.
    H = contribution_history(l, bn, ad, rate, 2000, sexes=(1,))
    c = ALL_COHORTS.i(birth)
    assert np.isclose(H.cum_indexed[c, YEARS.i(2049)], 45 * 20.)        # 残高 900（指数 1 なので名目 = 賃金評価）
    qp = np.zeros((100, 130, 3))
    qp[:, 80:, :] = 1.                                    # 80 歳の途中で必ず死ぬ → 現価率 = 65〜80 の 16 年 − 0.5 = 15.5
    N = ndc(H, qp, retire_age=65)
    assert np.isclose(N.divisor[c], 15.5) and np.isclose(N.balance[c], 900.) and np.isclose(N.pension[c], 900. / 15.5)
    assert np.isclose(N.per_head[c], 900. / 15.5)
    assert np.isclose(N.outgo[c, YEARS.i(2050)], 900. / 15.5) and N.outgo[c, YEARS.i(2066)] == 0.
    ib = np.zeros(ALL_COHORTS.n); ib[c] = 155.            # 移行: 旧制度の年額 10 × 現価率 15.5
    assert np.isclose(initial_balance_from_old(np.where(np.arange(ALL_COHORTS.n) == c, 10., 0.), N.divisor)[c], 155.)
    N2 = ndc(H, qp, retire_age=65, initial_balance=ib)
    assert np.isclose(N2.pension[c], (900. + 155.) / 15.5)
    assert np.isclose(minimum_guarantee(np.array([50., 80.]), 70.), np.array([20., 0.])).all()
    rec = np.zeros((ALL_COHORTS.n, YEARS.n)); rec[c, YEARS.i(2050)] = 3.
    assert flat(70., rec)[c, YEARS.i(2050)] == 210.


def test_世代別倍率の手計算():
    """拠出 20（2030）・40（2031）、給付 100（2040）。ad は 2030 = 2、2031 = 4、2040 以降 8。65 歳 = 2075 で評価:
    拠出の現価 = 20×8/2 + 40×8/4 = 160、給付の現価 = 100×8/8 = 100 → 倍率 0.625（本人分なら 1.25）。"""
    NC, NY = ALL_COHORTS.n, YEARS.n
    con = np.zeros((NC, NY)); ben = np.zeros((NC, NY)); ins = np.zeros((NC, NY)); ad = np.zeros(NY)
    c = ALL_COHORTS.i(2010)
    con[c, YEARS.i(2030)] = 20.; con[c, YEARS.i(2031)] = 40.; ben[c, YEARS.i(2040)] = 100.
    ad[YEARS.i(2030)] = 2.; ad[YEARS.i(2031)] = 4.; ad[YEARS.i(2032):] = 8.
    H = History(2021, ins, con, con, con.cumsum(1), con.cumsum(1), ad)
    G = generational_ratio(H, ben)
    assert np.isclose(G[2010][0], 0.625) and G[2010][1] is True
    assert np.isclose(generational_ratio(H, ben, employer=False)[2010][0], 1.25)
    assert generational_ratio(H, ben, births=[2000]) == {}                 # 拠出が無い生年度は出ない
