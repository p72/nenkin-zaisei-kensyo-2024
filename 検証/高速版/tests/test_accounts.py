# -*- coding: utf-8 -*-
"""勘定と流れ（`kosoku/accounts.py`、フェーズ I）— 港の①②を上流に③④⑤を回して恒等式を見る
================================================================================================
(1) 既定の yaml で全恒等式（収入計・支出計 = 部分和、積立金の漸化式、流れの from = to、拠出金 = 基礎年金
給付の頭割り）が相対 1e-9 で成り立つ、(2) `statement()` が⑤の列そのもの、(3) 統合しても恒等式が成り立ち
統合勘定の間の流れ（支援金）が消える、(4) 税方式化（`kiso_tax`）で各制度の拠出金と国庫負担が同額になり、
恒等式は保たれる。`work/suuri/rev2024` が無ければ飛ばす。玩具ケースは `tests/toy/test_accounts_toy.py`。
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
from kosoku import pipeline                                  # noqa: E402
from kosoku.accounts import ledger_of, identities, merge, statement   # noqa: E402
from kosoku.stages.s5_emp_shushi.shushi import C             # noqa: E402

CASE = "3001"
S = suuri_env.suuri


def _need(path):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        pytest.skip("無い: %s" % path)
    return path


def _run(tmp, *overlay):
    pol = load_policy(*overlay)
    up = {"waku": _need(S("wakuc", "rslt", "ver_4_1", "rslt" + CASE)), "kyufu": _need(S("emp", "rslt", "u-rev"))}
    _need(S("emp", "data", "u-rev", "econ", "econ-%s.csv" % CASE))
    res = pipeline.run(CASE, pol, S(), tmp, upstream_from=up, stages=("s3_nat", "s4_kiso_nenkin", "s5_emp_shushi"),
                       write_csv=False)
    return pol, res


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    pol, res = _run(str(tmp_path_factory.mktemp("acc_base")))
    return pol, res, ledger_of(pol, res["s5"], res["s4"])


@pytest.fixture(scope="module")
def tax(tmp_path_factory):
    pol, res = _run(str(tmp_path_factory.mktemp("acc_tax")), "kiso_tax")
    return pol, res, ledger_of(pol, res["s5"], res["s4"])


def test_既定の恒等式(base):
    _, _, L = base
    assert set(L.accounts) == {"kounen", "kokkyo", "chikyo", "shigaku", "kokunen", "kiso"}
    bad = [(n, d) for n, d, ok in identities(L) if not ok]
    assert not bad, bad
    assert len(identities(L)) >= 19


def test_statement_は収支計算の列そのもの(base):
    _, res, L = base
    Cc = res["s5"].Cc
    i1, ie = YEARS.i(L.years[0]), YEARS.i(L.years[1])
    for s, name in enumerate(("kounen", "kokkyo", "chikyo", "shigaku")):
        st = statement(L.accounts[name])
        assert np.allclose(st["収入計"][i1:ie + 1], Cc[s, C.SHUNYU, i1:ie + 1], rtol=1e-12)
        assert np.allclose(st["支出計"][i1:ie + 1], Cc[s, C.SHISHUTU, i1:ie + 1], rtol=1e-12)
        assert np.allclose(st["収支差"][i1:ie + 1], Cc[s, C.SHUSHISA, i1:ie + 1], rtol=1e-9)
        assert st["積立金"] is not None


def test_流れの向きと大きさ(base):
    _, _, L = base
    i = YEARS.i(2050)
    t = L.transfers["kiso_kyoshutsu"]
    assert set(t.series) == {"kounen", "kokkyo", "chikyo", "shigaku", "kokunen", "kiso"}
    assert t.series["kiso"][i] > t.series["kounen"][i] > t.series["kokunen"][i] > 0
    k = L.transfers["kokko_kiso"]
    assert np.isclose(k.series["kounen"][i], 0.5 * t.series["kounen"][i], rtol=1e-6)   # 国庫負担割合 1/2
    assert np.isclose(k.series["treasury"][i], sum(k.series[n][i] for n in k.to))
    assert L.transfers["shien"].series["kounen"][i] == 0.                             # 通常試算では支援金 0


def test_統合(base):
    _, _, L = base
    M = merge(L, ["kounen", "kokkyo", "chikyo", "shigaku"], "employee_all")
    assert "employee_all" in M.accounts and "kounen" not in M.accounts
    assert "shien" not in M.transfers                          # 統合した勘定の間で閉じる流れは消える
    bad = [(n, d) for n, d, ok in identities(M) if not ok]
    assert not bad, bad
    i = YEARS.i(2050)
    a = M.accounts["employee_all"]
    assert np.isclose(statement(a)["収入計"][i], sum(statement(L.accounts[n])["収入計"][i] for n in a.members))
    assert np.isclose(M.transfers["kiso_kyoshutsu"].series["employee_all"][i],
                      sum(L.transfers["kiso_kyoshutsu"].series[n][i] for n in a.members))
    with pytest.raises(ValueError):
        merge(L, ["kounen", "kokunen"], "x")


def test_税方式化(base, tax):
    _, res0, L0 = base
    pol, res, L = tax
    assert pol.get("kiso.kokko.after") == 1.0
    bad = [(n, d) for n, d, ok in identities(L) if not ok]
    assert not bad, bad
    i = YEARS.i(2050)
    for n in ("kounen", "kokkyo", "chikyo", "shigaku"):
        a = L.accounts[n]
        assert np.isclose(a.flows["国庫負担(基礎)"][i], a.flows["基礎年金拠出金"][i], rtol=1e-12)   # 拠出金 = 国庫
        assert a.flows["国庫負担(基礎)"][i] > L0.accounts[n].flows["国庫負担(基礎)"][i] * 1.5
    k = L.transfers["kokko_kiso"]
    assert np.isclose(k.series["treasury"][i], L.transfers["kiso_kyoshutsu"].series["kiso"][i], rtol=1e-12)
    # 基礎年金が全額国庫なら国年の調整は要らない（終了年度 = 実績年度）。所得代替率は調整なしの水準
    assert res["s5"].out.owari["kend_t"] == 2024
    assert res["s5"].out.final_rate["total"] > res0["s5"].out.final_rate["total"]
