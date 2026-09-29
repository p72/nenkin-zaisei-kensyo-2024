# -*- coding: utf-8 -*-
"""拠出履歴と給付設計（`kosoku/history.py` `kosoku/benefit_formula.py`、フェーズ J）— 実データ（ケース 3001）
==============================================================================================================
②厚年を高速版で回し（約 40 秒）、①の外枠 `l` と②の標準報酬 `bn`・賃金指数 `ad`、⑤の保険料率から拠出履歴を
積む。見るのは (1) 生年度で積んだ拠出の年度計が⑤の厚年の保険料収入と 2% 以内（年度末の人数・部分の
違いだけ）、(2) 年金現価率が 20〜30 年（コホート別の生命表）、(3) NDC の給付が正で裁定後は賃金スライド、
(4) 世代別の給付負担倍率が窓に入る生年度で 厚労省の公表（厚年の若い世代は本人負担分で 2.3 倍前後）と
同じ桁。`work/suuri/rev2024` が無ければ飛ばす。玩具ケースは `tests/toy/test_benefit_toy.py`。
"""
import os
import sys

import numpy as np
import pytest

from conftest import FAST
sys.path.insert(0, os.path.normpath(os.path.join(FAST, "..")))
import suuri_env                                            # noqa: E402

from kosoku.axis import YEARS, ALL_COHORTS                   # noqa: E402
from kosoku.policy import load_policy                        # noqa: E402
from kosoku.history import contribution_history, by_cohort   # noqa: E402
from kosoku.benefit_formula import ndc, generational_ratio, cohort_survival, annuity_divisor   # noqa: E402
from kosoku.stages.s2_emp_kyufu import run as KY             # noqa: E402
from kosoku.stages.s5_emp_shushi import run as RUN           # noqa: E402
from kosoku.stages.s5_emp_shushi.shushi import C             # noqa: E402

CASE = "3001"
S = suuri_env.suuri


def _need(path):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        pytest.skip("無い: %s" % path)
    return path


@pytest.fixture(scope="module")
def data():
    pol = load_policy()
    inp = KY.read_inputs(pol, "kou", CASE, _need(S("emp")), _need(S("wakuc", "rslt", "ver_4_1", "rslt" + CASE)),
                         _need(S("emp", "data", "u-rev", "econ", "econ-%s.csv" % CASE)),
                         _need(S("emp", "data", "u-sinj", "QX-M2023.csv")))
    r2 = KY.run_system(inp)
    inp5 = RUN.read_inputs(pol, CASE, S("emp"), _need(S("bas")), _need(S("nat")),
                           S("wakuc", "rslt", "ver_4_1", "rslt" + CASE), S("emp", "data", "u-rev", "econ", "econ-%s.csv" % CASE))
    r5 = RUN.run(inp5, CASE)
    H = contribution_history(inp.l, r2.ctxs[1].hs.bn, r2.E.ad, r5.prem.rate["kou"], 2021)
    return pol, inp, r2, r5, H


def test_拠出の年度計は厚年の保険料収入と合う(data):
    _, _, _, r5, H = data
    tot = H.contrib.sum(0)
    for y in (2025, 2030, 2050, 2100):
        i = YEARS.i(y)
        assert abs(tot[i] / r5.Cc[0, C.HOKENRYO, i] - 1.) < 0.02, y
    assert (H.cum_indexed[:, YEARS.i(2100)] >= H.cum_nominal[:, YEARS.i(2100)] - 1e-6).all()   # 賃金は上がる


def test_年金現価率とNDC(data):
    _, inp, _, _, H = data
    lm, lf = cohort_survival(inp.qp, 1960, 1), cohort_survival(inp.qp, 1960, 2)
    assert 0.9 < lm[65] < lf[65] < 1.0 and lm[85] < lf[85]
    assert 20. < annuity_divisor(lm, 65) < annuity_divisor(lf, 65) < 30.
    N = ndc(H, inp.qp, retire_age=65)
    c = ALL_COHORTS.i(2006)                                   # 拠出の全期間が窓に入る最初の生年度
    assert N.balance[c] > 0 and N.pension[c] > 0 and 20. < N.divisor[c] < 30.
    i = YEARS.i(2006 + 65)
    assert np.isclose(N.outgo[c, i], N.pension[c])
    lm = (cohort_survival(inp.qp, 2006, 1) + cohort_survival(inp.qp, 2006, 2)) / 2.
    assert np.isclose(N.outgo[c, i + 1] / N.outgo[c, i], H.ad[i + 1] / H.ad[i] * lm[66] / lm[65])   # 賃金スライド × 生存
    assert N.outgo[c, i + 10] < N.outgo[c, i] * H.ad[i + 10] / H.ad[i]                        # 生存率で減る
    assert N.per_head[c] > 1e6                                                                # 1 人あたり年額（名目）


def test_世代別の給付負担倍率(data):
    _, _, _, r5, H = data
    ben = r5.ben
    B = by_cohort(ben[0, 0] + ben[0, 1] + ben[0, 2] + ben[0, 10], 0, 1)             # 独自 ＋ 基礎（国庫込み）
    Bx = by_cohort(ben[0, 0] + ben[0, 1] + ben[0, 2] - ben[0, 3] - ben[0, 4] - ben[0, 5] + ben[0, 10] - ben[0, 11], 0, 1)
    G = generational_ratio(H, B)
    Gx = generational_ratio(H, Bx)
    Gh = generational_ratio(H, B, employer=False)
    done = [b for b, (r, ok) in G.items() if ok]
    assert done and min(done) == 2006 and max(done) == 2025
    for b in done:
        assert 1.0 < G[b][0] < 1.5, (b, G[b])               # 国庫込み・事業主込み
        assert 0.7 < Gx[b][0] < 1.2, (b, Gx[b])             # 国庫除く
        assert 2.0 < Gh[b][0] < 3.0, (b, Gh[b])             # 本人負担分（厚労省の公表は若い世代で 2.3 倍前後）
        assert np.isclose(Gh[b][0], 2. * G[b][0])
    assert G[2000][1] is False                              # 窓に入らない生年度は complete=False
