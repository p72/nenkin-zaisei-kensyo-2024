# -*- coding: utf-8 -*-
"""②厚生年金給付費推計の通し（フェーズ D の受け入れ）— 原本 C の出力との突き合わせ
==================================================================================
`work/suuri/rev2024` に②の入力と原本 C（`emp/exec/nenkin` 相当）の出力が無ければ飛ばす。

1. 4 制度の `shus.*`（⑤が読む系列）・`kiso.*`（④が読む行）・`kaitea/b` を原本と比べる。
   計画の受け入れは相対 1e-4。実測は 1e-13 前後（`README.md`）。
   既定の policy は J2（地共済の `ab` の係数 461.6518）も原本どおりなので、地共済の国庫負担の
   算定対象（`KFPRX`）も同じ許容で比べる。`fix_bugs` では原本の 1/1000 になる（`README.md` フェーズ D）
2. 高速版②の出力を④⑤に食わせる（`emp_kiso_dir` / `kyufu_dir`）。最終所得代替率 ±0.5%pt、
   終了年度 ±1（計画の表 D「その後 B・C を高速版②で再実行」）
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
from kosoku.io_port import read_year_age_table               # noqa: E402
from kosoku.stages.s2_emp_kyufu import run as R              # noqa: E402
from kosoku.stages.s2_emp_kyufu.output import to_port_csv    # noqa: E402
from kosoku.stages.s5_emp_shushi import inputs as S5         # noqa: E402

CASE = "3001"
S = suuri_env.suuri
SYSTEMS = ("kou", "kok", "ren", "sig")
FIELDS = ("ap", "ap65", "a", "a60", "a65", "a70", "aiku", "t4", "hirei", "teigaku", "kakyu",
          "kokko_hirei", "kokko_teigaku", "kokko_kasaage")


def _need(path):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        pytest.skip("無い: %s" % path)
    return path


def _port_shus(name):
    return _need(S("emp", "rslt", "u-rev", "shus", "shus.%s-%s-%s_%s" % ((CASE,) * 3 + (name,))))


@pytest.fixture(scope="module")
def fast(tmp_path_factory):
    """4 制度を高速版で回して港の配置で書く（約 2 分）。"""
    for name in SYSTEMS:
        _port_shus(name)
        _need(S("emp", "rslt", "u-rev", "kiso", "kiso.%s-%s-%s_%s" % ((CASE,) * 3 + (name,))))
    pol = load_policy()
    out = str(tmp_path_factory.mktemp("s2_fast"))
    runs = R.run(pol, CASE, _need(S("emp")), _need(S("wakuc", "rslt", "ver_4_1", "rslt" + CASE)),
                 _need(S("emp", "data", "u-rev", "econ", "econ-%s.csv" % CASE)),
                 _need(S("emp", "data", "u-sinj", "QX-M2023.csv")))
    paths = to_port_csv(runs, CASE, out)
    return runs, paths, out


def _rel(a, b):
    return np.abs(a - b) / np.maximum(np.abs(b), 1.)


@pytest.mark.parametrize("name", SYSTEMS)
def test_shusの系列が原本と一致(fast, name):
    runs, paths, _ = fast
    mine, port = S5.read_shus(paths[name]["shus"]), S5.read_shus(_port_shus(name))
    for f in FIELDS:
        m, p = getattr(mine, f), getattr(port, f)
        tight = 1e-8                                       # 実測（ロジック忠実で丸め順だけ違う。kfprx は 6e-11）
        w = _rel(m, p).max()
        assert w <= 1e-4, (name, f, w)
        assert w <= tight, (name, f, w)
    assert runs[name].out.prov.chain() == (("s2", "fast"),)


def _kiso_rows(path):
    out = {}
    for l in open(path, encoding="utf-8", errors="replace"):
        f = [x.strip() for x in l.split(",")]
        if not f or not f[0].lstrip("-").isdigit():
            continue
        n = 6 if f[1] == "1" else 4
        try:
            out[tuple(int(v) for v in f[:n])] = np.array([float(v) for v in f[n:]])
        except ValueError:
            continue
    return out


@pytest.mark.parametrize("name", SYSTEMS)
def test_kisoの行が原本と一致(fast, name):
    _, paths, _ = fast
    kij = YEARS.i(load_policy().get("kounen.years.kijun"))
    mine = _kiso_rows(paths[name]["kiso"])
    port = _kiso_rows(S("emp", "rslt", "u-rev", "kiso", "kiso.%s-%s-%s_%s" % ((CASE,) * 3 + (name,))))
    assert set(mine) == set(port)
    worst = max(_rel(mine[k], v).max() for k, v in port.items() if k[0] >= kij)
    assert worst <= 1e-6, worst


def test_改定率kaiteが原本と一致(fast):
    _, paths, _ = fast
    for tag in ("kaitea", "kaiteb"):
        m = read_year_age_table(paths["kou"][tag], YEARS.first, first_age=67)
        p = read_year_age_table(_need(S("emp", "rslt", "u-rev", "kaite", "%s-%s-%se" % (tag, CASE, CASE))),
                                YEARS.first, first_age=67)
        assert np.abs(m - p).max() <= 1e-12


def test_高速版の厚年給付費を基礎年金と収支計算に食わせても看板の数字は範囲内(fast):
    """③④は港の CSV、②だけ高速版。最終所得代替率は港の値 56.912 から ±0.5%pt、終了年度 ±1。"""
    from kosoku.stages.s4_kiso_nenkin import run as KISO
    from kosoku.stages.s5_emp_shushi import run as RUN
    _, paths, out = fast
    pol = load_policy()
    nat_dir = _need(S("nat"))
    waku = _need(S("wakuc", "rslt", "ver_4_1", "rslt" + CASE))
    econ = _need(S("emp", "data", "u-rev", "econ", "econ-%s.csv" % CASE))
    _need(S("bas", "rslt", "kekka%s-%s-%s-%s-1120-000a.csv" % ((CASE,) * 4)))
    kinp = KISO.read_inputs(pol, CASE, nat_dir, os.path.join(out, "kiso"), waku, _need(S("bas")), econ)
    kr = KISO.run(kinp, CASE)
    inp = RUN.read_inputs(pol, CASE, _need(S("emp")), _need(S("bas")), nat_dir, waku, econ, kiso=kr,
                          kyufu_dir=out)
    r = RUN.run(inp, CASE)
    f = r.out.final_rate
    assert abs(f["total"] - 56.9122495807027) <= 0.5
    assert abs(f["hirei"] - 24.9711420191125) <= 0.5
    assert abs(f["kiso"] - 31.9411075615902) <= 0.5
    assert abs(r.out.owari["kend_h"] - 2024) <= 1
    assert abs(r.out.owari["kend_t"] - 2039) <= 1
    assert r.out.owari["ok"]


def test_労働参加のシナリオで厚年の生存脱退力の縮小が変わる():
    """`flg_inout`（`run_pipeline.sh` の ROUDR − 1）: 0 進展は 40〜59 歳を 20%・60〜64 歳を 40%（男）縮小、
    1 漸進は 60〜64 歳だけ 30%、2 現状は縮小しない（港 emp_kyufu/kiso.py:224-262 は rds を 0 のまま）。
    縮小は 2040 年度（`kounen.kiso.rds_end_year`）で終わる。"""
    from kosoku.stages.s2_emp_kyufu.kiso import kiso_rates
    from kosoku.stages.s2_emp_kyufu.sknr import shikyu_kaishi
    pol = load_policy()
    inp = R.read_inputs(pol, "kou", CASE, _need(S("emp")), _need(S("wakuc", "rslt", "ver_4_1", "rslt" + CASE)),
                        _need(S("emp", "data", "u-rev", "econ", "econ-%s.csv" % CASE)),
                        _need(S("emp", "data", "u-sinj", "QX-M2023.csv")))
    sk = shikyu_kaishi(pol, 1, 1)
    K = {f: kiso_rates(pol, inp.kisor[1], inp.qp, 0, 1, sk, flg_inout=f) for f in (0, 1, 2)}
    k0, ke = YEARS.i(pol.get("kounen.years.kijun")), YEARS.i(pol.get("kounen.kiso.rds_end_year"))
    u0 = K[0].u[k0, :, 1]
    assert u0[45] > 0 and u0[62] > 0
    for f, r45, r62 in ((0, 0.20, 0.40), (1, 0.00, 0.30), (2, 0.00, 0.00)):
        u = K[f].u
        assert np.isclose(u[ke, 45, 1], u0[45] * (1. - r45)), f
        assert np.isclose(u[ke, 62, 1], u0[62] * (1. - r62)), f
        assert np.isclose(u[ke + 10, 62, 1], u[ke, 62, 1]), f                 # 終わったあとは据え置き
        mid = (k0 + ke) // 2                                                  # 途中は線形
        assert np.isclose(u[mid, 62, 1], u0[62] * (1. - r62 * (mid - k0) / float(ke - k0))), f
