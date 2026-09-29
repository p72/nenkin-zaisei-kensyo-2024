# -*- coding: utf-8 -*-
"""①被保険者推計の通し（フェーズ E の受け入れ）— 移植版①の CSV との突き合わせ
================================================================================
`work/suuri/rev2024/wakuc/` に①の入力と移植版①の出力（`rslt/ver_4_1/rslt3001/`。原本と
103/104 本がバイト一致する）が無ければ飛ばす。

1. 58 分類 × 5 性 × 年度 2021〜2125 × 15〜100 歳を比べる。港は人数を整数に丸めて書くので、
   高速版も同じ丸めを掛けてから、**1 人以内か相対 1e-6**（丸めの境目で 1 人ずれる）。計の列も
2. 調整率（`waku-m`）は **0.001 の桁まで完全一致**（実測は 0.0001 の桁まで完全一致）
3. 適用拡大（MODE = 1）でも走り、1 段階目の列（26〜41）に値が入る。2 段階目（42〜57）は同梱の
   `partnin2020-2029-N.csv` が `-2027-N.csv` と同じ内容なので 0（港も 0。5 つの MODE すべて）
4. 高速版①の CSV を③④⑤（②は港の CSV）に食わせても最終所得代替率と終了年度は港の値のまま
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
from kosoku.io_port import read_waku_class, read_waku_m      # noqa: E402
from kosoku.stages.s1_hihokensha import run as R             # noqa: E402
from kosoku.stages.s1_hihokensha.cutritu import raund        # noqa: E402
from kosoku.stages.s1_hihokensha.output import to_port_csv, NB   # noqa: E402

CASE = "3001"
S = suuri_env.suuri
LO, HI = 15, 100


def _need(path):
    if not os.path.exists(path):
        pytest.skip("無い: %s" % path)
    return path


def _port_dir():
    return _need(S("wakuc", "rslt", "ver_4_1", "rslt" + CASE))


@pytest.fixture(scope="module")
def fast(tmp_path_factory):
    """高速版①（試算 3001 の設定: 出生中位・死亡中位・入国 16 万・労働参加進展・適用拡大なし）。"""
    _need(S("wakuc", "data", "sinj", "pop1-110.csv"))
    _need(os.path.join(_port_dir(), "waku%s-00.csv" % CASE))
    pol = load_policy()
    r = R.run(R.read_inputs(pol, S("wakuc", "data")), CASE)
    out = str(tmp_path_factory.mktemp("s1_fast"))
    paths = to_port_csv(r, CASE, out)
    return r, paths, out


def _compare_class(count, port_path, b):
    tables, totals = read_waku_class(port_path)
    ys = YEARS.s(2021, 2125)
    worst_abs, worst_rel, bad = 0., 0., 0
    for (bb, s), pt in tables.items():
        assert bb == b
        m = raund(count[b, ys, s, LO:HI + 1], 0)
        p = pt[ys, LO:HI + 1]
        d = np.abs(m - p)
        rel = d / np.maximum(np.abs(p), 1.)
        bad += int(((d > 1.) & (rel > 1e-6)).sum())
        worst_abs, worst_rel = max(worst_abs, d.max()), max(worst_rel, rel.max())
        mt = raund(count[b, ys, s, LO:HI + 1].sum(1), 0)
        dt = np.abs(mt - totals[(bb, s)][ys])
        bad += int(((dt > 1.) & (dt / np.maximum(np.abs(totals[(bb, s)][ys]), 1.) > 1e-6)).sum())
    return bad, worst_abs, worst_rel


@pytest.mark.parametrize("b", range(NB))
def test_分類別の人数が移植版と一致(fast, b):
    r, _, _ = fast
    bad, worst_abs, worst_rel = _compare_class(r.out.count, os.path.join(_port_dir(), "waku%s-%02d.csv" % (CASE, b)), b)
    assert bad == 0, (b, worst_abs, worst_rel)
    assert worst_abs <= 1.                                   # 丸めの境目の 1 人だけ


def test_調整率が移植版と一致(fast):
    r, paths, _ = fast
    port = read_waku_m(os.path.join(_port_dir(), "waku%s-m.csv" % CASE))
    mine = r.out.cutritu
    ys = YEARS.s(2005, 2125)
    assert np.abs(mine[ys] - port[ys]).max() < 5e-4           # 計画の受け入れ: 0.001 で完全一致
    assert np.abs(mine[ys] - port[ys]).max() == 0.            # 実測: 小数 4 桁で完全一致
    assert np.array_equal(read_waku_m(paths["m"]), mine)      # 書いた CSV の往復
    assert r.out.prov.chain() == (("s1", "fast"),)
    assert r.H.notes == []


def test_書いたcsvは読み手で往復する(fast):
    r, paths, _ = fast
    t, tot = read_waku_class(paths["waku"][20])               # 人口（年央）
    ys = YEARS.s(2021, 2125)
    for s in range(5):
        assert np.array_equal(t[(20, s)][ys, LO:HI + 1], raund(r.out.count[20, ys, s, LO:HI + 1], 0))
    assert set(k[1] for k in t) == {0, 1, 2, 3, 4}


def test_適用拡大でも走る():
    """MODE = 1（適用拡大①。2027・2029 年度の 2 段階）。港の `partnin2020-2027-1.csv` などを読む。"""
    _need(S("wakuc", "data", "part", "partnin2020-2027-1.csv"))
    pol = load_policy()
    r = R.run(R.read_inputs(pol, S("wakuc", "data"), mode=1), CASE)
    c = r.out.count
    assert r.S.part == 2 and r.S.partyr1 == 2027 and r.S.partyr2 == 2029
    assert c[26, YEARS.i(2026)].sum() == 0. and c[26, YEARS.i(2027)].sum() > 0.    # 1 段階目
    assert c[42].sum() == 0.                        # 2 段階目: 同梱の 2029 のファイルは 2027 と同じ内容（港も 0）
    assert c[7, YEARS.i(2027)].sum() > c[7, YEARS.i(2026)].sum()                   # パートが増える
    assert r.H.notes == []


def test_高速版の外枠を基礎年金と収支計算に食わせても看板の数字は港のまま(fast):
    """①だけ高速版、②③は港の CSV、④⑤は高速版。最終所得代替率 56.912、終了年度 2024/2039。"""
    from kosoku.stages.s3_nat import run as NAT
    from kosoku.stages.s4_kiso_nenkin import run as KISO
    from kosoku.stages.s5_emp_shushi import run as RUN
    _, _, out = fast
    pol = load_policy()
    nat_dir = _need(S("nat"))
    econ = _need(S("emp", "data", "u-rev", "econ", "econ-%s.csv" % CASE))
    _need(S("emp", "rslt", "u-rev", "kiso", "kiso.%s-%s-%s_kou" % ((CASE,) * 3)))
    _need(S("bas", "rslt", "kekka%s-%s-%s-%s-1120-000a.csv" % ((CASE,) * 4)))
    nat = NAT.run(NAT.read_inputs(pol, nat_dir, out, CASE, econ), CASE)
    kinp = KISO.read_inputs(pol, CASE, nat_dir, S("emp", "rslt", "u-rev", "kiso"), out, _need(S("bas")), econ,
                            nat_out=nat.out)
    kr = KISO.run(kinp, CASE)
    inp = RUN.read_inputs(pol, CASE, _need(S("emp")), _need(S("bas")), nat_dir, out, econ, kiso=kr,
                          nat_out=nat.out)
    r = RUN.run(inp, CASE)
    f = r.out.final_rate
    assert abs(f["total"] - 56.9122495807027) <= 0.5
    assert abs(r.out.owari["kend_h"] - 2024) <= 1
    assert abs(r.out.owari["kend_t"] - 2039) <= 1
    assert r.out.owari["ok"]
