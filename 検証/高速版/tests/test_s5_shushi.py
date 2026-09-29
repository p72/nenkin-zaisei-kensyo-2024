# -*- coding: utf-8 -*-
"""⑤厚生年金収支計算の通し（フェーズ C の受け入れ）— 原本 C の出力との突き合わせ
================================================================================
`work/suuri/rev2024` に⑤の入力と原本 C（`emp/exec/asys20`）の出力が無ければ飛ばす。

2通りの上流で比べる（`計画.md` 表C と「累積ドリフトを段階ごとに帰属させる」）
    port  ②③④の入力に原本の CSV（shus.* / KYOSHUTUKIN / TUMATUMI / cuta / KOKUKAITE）
          → ⑤の数理だけの差。`01shushi` の 31列 × 5制度 × 調整前後、`03summary` の
            所得代替率、`cuta/cutb` が 1e-6（実測 1e-12）。最終所得代替率は 1e-9
    fast  ③④に高速版（既定の policy = 原本の癖どおり）を使う
          → ③④の癖の修正が⑤へ伝わる分。最終所得代替率 ±0.5%pt（計画の受け入れ）、
            厚年の終了年度 ±1、31列は相対 1e-2 の範囲

公表値（詳細結果等1 の財政見通し xlsx、`papers/001286770`）とは 3001 だけ比べる。
`work/` の 3003・3004 は既定の外枠（労働参加の選択が公表と違う）で作ってあるので、
原本 C との一致だけを見る。
"""
import glob
import os
import sys

import numpy as np
import pytest

from conftest import FAST
sys.path.insert(0, os.path.normpath(os.path.join(FAST, "..")))
sys.path.insert(0, os.path.normpath(os.path.join(FAST, "..", "オプション試算")))
import suuri_env                                            # noqa: E402

from kosoku.axis import YEARS                                # noqa: E402
from kosoku.policy import load_policy                        # noqa: E402
from kosoku.stages.s3_nat import run as NAT                  # noqa: E402
from kosoku.stages.s4_kiso_nenkin import run as KISO         # noqa: E402
from kosoku.stages.s5_emp_shushi import run as RUN           # noqa: E402
from kosoku.stages.s5_emp_shushi.output import (to_port_csv, read_shushi, read_summary, read_cut,
                                                 TITLE_BEFORE, TITLE_AFTER, COLS_SHUSHI, SYS_OUT)  # noqa: E402

CASE = "3001"
S = suuri_env.suuri
REPO = os.path.normpath(os.path.join(FAST, "..", ".."))
PUBLISHED = os.path.join(REPO, "papers", "001286770", "財政検証詳細結果等", "03財政検証詳細結果",
                         "01財政見通し", "01.　人口中位　高成長実現ケース.xlsx")


def _need(path):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        pytest.skip("無い: %s" % path)
    return path


def _port_paths(case):
    d = S("emp", "rslt", "ez_arev")
    p = {name: os.path.join(d, "shushi", "01shushi.%s-%s-%s-%s-1120-000e_08%s.csv" % ((case,) * 4 + (name,)))
         for name in SYS_OUT}
    p["summary"] = os.path.join(d, "shushi", "03summary.%s-%s-%s-%s-1120-000_08sum.csv" % ((case,) * 4))
    p["cuta"] = os.path.join(d, "cutr", "cuta-%s-%s-%s-%s-1120-000.csv" % ((case,) * 4))
    p["cutb"] = os.path.join(d, "cutr", "cutb-%s-%s-%s-%s-1120-000.csv" % ((case,) * 4))
    for v in p.values():
        _need(v)
    return p


def _inputs(pol, case, kiso=None, nat_out=None):
    return RUN.read_inputs(pol, case, _need(S("emp")), _need(S("bas")), _need(S("nat")),
                           _need(S("wakuc", "rslt", "ver_4_1", "rslt" + case)),
                           _need(S("emp", "data", "u-rev", "econ", "econ-%s.csv" % case)),
                           kiso=kiso, nat_out=nat_out)


def _run(tmp, case, kiso=None, nat_out=None):
    _need(S("emp", "rslt", "u-rev", "shus", "shus.%s-%s-%s_kou" % ((case,) * 3)))
    pol = load_policy()
    inp = _inputs(pol, case, kiso, nat_out)
    r = RUN.run(inp, case)
    return r, to_port_csv(r, case, tmp)


@pytest.fixture(scope="module")
def from_port(tmp_path_factory):
    return _run(str(tmp_path_factory.mktemp("s5_port")), CASE)


@pytest.fixture(scope="module")
def from_fast(tmp_path_factory):
    """③④を高速版で回してから⑤。"""
    pol = load_policy()
    nat_dir = _need(S("nat"))
    waku = _need(S("wakuc", "rslt", "ver_4_1", "rslt" + CASE))
    econ = _need(S("emp", "data", "u-rev", "econ", "econ-%s.csv" % CASE))
    nr = NAT.run(NAT.read_inputs(pol, nat_dir, waku, CASE, econ), CASE)
    kinp = KISO.read_inputs(pol, CASE, nat_dir, _need(S("emp", "rslt", "u-rev", "kiso")), waku,
                            _need(S("bas")), econ, nat_out=nr.out)
    kr = KISO.run(kinp, CASE)
    return _run(str(tmp_path_factory.mktemp("s5_fast")), CASE, kiso=kr, nat_out=nr.out), kr


def _worst(mine, port, skip=()):
    """{年度: 配列} 同士の最大相対差（分母が小さい欄は絶対差）。"""
    worst, where = 0., None
    for y, p in port.items():
        m = mine[y]
        assert len(m) == len(p), (y, len(m), len(p))
        d = np.abs(m - p)
        r = np.where(np.abs(p) > 1e-3, d / np.maximum(np.abs(p), 1e-300), d)
        for i in skip:
            r[i] = 0.
        i = int(np.argmax(r))
        if r[i] > worst:
            worst, where = float(r[i]), (y, COLS_SHUSHI[i], m[i], p[i])
    return worst, where


# ---------------------------------------------------------------- 原本の②③④を上流に

def test_最終所得代替率と終了年度(from_port):
    r, _ = from_port
    ps = read_summary(_port_paths(CASE)["summary"])
    f = r.out.final_rate
    np.testing.assert_allclose(f["total"], 56.9122495807027, rtol=1e-9)
    np.testing.assert_allclose(f["hirei"], 24.9711420191125, rtol=1e-9)
    np.testing.assert_allclose(f["kiso"], 31.9411075615902, rtol=1e-9)
    assert r.out.owari["kend_h"] == ps["kend"]["厚年"][0] == 2024
    assert r.out.owari["kend_t"] == ps["kend"]["国年"][0] == 2039
    np.testing.assert_allclose(r.out.owari["cut_h"], ps["kend"]["厚年"][1], rtol=1e-9)
    np.testing.assert_allclose(r.out.owari["cut_t"], ps["kend"]["国年"][1], rtol=1e-9)
    assert r.out.owari["ok"]


@pytest.mark.parametrize("name", SYS_OUT)
def test_01shushiの31列が原本と一致(from_port, name):
    _, paths = from_port
    mine, port = read_shushi(paths[name]), read_shushi(_port_paths(CASE)[name])
    for title in (TITLE_BEFORE, TITLE_AFTER):
        w, where = _worst(mine[title], port[title])
        assert w <= 1e-6, "%s %s: %s" % (name, title, where)
    assert mine["kend"] == port["kend"]


def test_03summaryの所得代替率が原本と一致(from_port):
    _, paths = from_port
    mine, port = read_summary(paths["summary"]), read_summary(_port_paths(CASE)["summary"])
    assert mine["kend"] == port["kend"]
    for y, p in port["table"].items():
        m = mine["table"][y]
        for k in ("所得代替率", "所得代替率(比例)", "所得代替率(基礎)", "比例カット67", "基礎カット67",
                  "モデル年金額", "可処分所得", "モデル年金額（物価割り戻し）"):
            np.testing.assert_allclose(m[k], p[k], rtol=1e-6, atol=1e-9, err_msg="%d %s" % (y, k))


def test_cutaとcutbが原本と一致(from_port):
    _, paths = from_port
    P = _port_paths(CASE)
    for k in ("cuta", "cutb"):
        mine, port = read_cut(paths[k]), read_cut(P[k])
        for y, p in port.items():
            np.testing.assert_allclose(mine[y], p, rtol=1e-9, atol=1e-12, err_msg="%s %d" % (k, y))


@pytest.mark.parametrize("case", ["3003", "3004"])
def test_他の経済前提でも原本と一致(tmp_path, case):
    """割線法が走る経路（3003: 年度走査 4 回＋割線法 1 回、3004: 30 回＋1 回）。"""
    P = _port_paths(case)
    r, paths = _run(str(tmp_path), case)
    ps = read_summary(P["summary"])
    assert r.out.owari["kend_h"] == ps["kend"]["厚年"][0]
    assert r.out.owari["kend_t"] == ps["kend"]["国年"][0]
    np.testing.assert_allclose(r.out.owari["cut_h"], ps["kend"]["厚年"][1], rtol=1e-9)
    last = max(ps["table"])
    np.testing.assert_allclose(r.out.final_rate["total"], ps["table"][last]["所得代替率"], rtol=1e-9)
    for name in SYS_OUT:
        w, where = _worst(read_shushi(paths[name])[TITLE_AFTER], read_shushi(P[name])[TITLE_AFTER])
        assert w <= 1e-6, "%s: %s" % (name, where)


def test_公表値の所得代替率(from_port):
    """詳細結果等1 の財政見通し（一元化レイアウト）と。計画の受け入れは ±0.5%pt。原本 C は
    公表値と 1e-12 で一致する（`検証/オプション試算/`）ので、実測はそれと同じ桁。"""
    _need(PUBLISHED)
    import compare_option as CO
    pub = CO.read_published(PUBLISHED)
    r, paths = from_port
    f = r.out.final_rate
    for key, mine in (("計", f["total"]), ("比例", f["hirei"]), ("基礎", f["kiso"])):
        p = pub["代替率"][key]
        assert abs(mine / 100. - p) <= 0.5e-2, (key, mine, p)
        assert abs(mine / 100. - p) <= 1e-9, (key, mine, p)
    sheet = pub["sheets"].get(CO.UNIFIED_SHEET) or pub["sheets"]["厚生年金"]     # 通常試算は制度別レイアウト
    series = sheet["所得代替率"]
    table = read_summary(paths["summary"])["table"]
    for y, p in series.items():
        if y in table:
            assert abs(table[y]["所得代替率"] / 100. - p) <= 0.5e-2, (y, table[y]["所得代替率"], p)


# ---------------------------------------------------------------- 高速版の③④を上流に

def test_高速版の国年と基礎年金を上流にしても看板の数字は範囲内(from_fast):
    """既定の policy は③の癖（B11・J3）も原本どおりなので、③④を高速版にしても⑤は原本と
    丸め順の差まで一致する（実測 2026-09-29: 最終所得代替率 13 桁、31列 1e-13）。"""
    (r, paths), kr = from_fast
    f = r.out.final_rate
    assert abs(f["total"] - 56.9122495807027) <= 1e-9
    assert abs(f["hirei"] - 24.9711420191125) <= 1e-9
    assert abs(f["kiso"] - 31.9411075615902) <= 1e-9
    assert r.out.owari["kend_h"] == 2024
    assert r.out.owari["kend_t"] == kr.sol.s_c_nendo
    P = _port_paths(CASE)
    for name in SYS_OUT:
        w, where = _worst(read_shushi(paths[name])[TITLE_AFTER], read_shushi(P[name])[TITLE_AFTER])
        assert w <= 1e-10, "%s: %s" % (name, where)
    assert r.out.prov.chain() == (("s4", "fast"), ("s5", "fast"))
    assert r.out.prov.upstream[0].chain() == (("s3", "fast"), ("s4", "fast"))
