# -*- coding: utf-8 -*-
"""④基礎年金の通し（フェーズ B の受け入れ）— 移植版④の出力との突き合わせ
==========================================================================
`work/suuri/rev2024` が無ければ飛ばす。ケース 3001。

2通りの上流で比べる（`計画.md` 表B と「累積ドリフトを段階ごとに帰属させる」）
    port  ③の入力に移植版③の CSV（KISONENKIN・DOKUZI・KOKUKAITE）
          → ④の数理だけの差。KYOSHUTUKIN・cuta・TUMATUMI・kekka の全ブロックが 1e-6
            （実測 1e-14）、終了年度・最終カット率が一致
    fast  ③の入力に高速版③（既定の policy = 原本の癖どおり）
          → ③④を通した丸め順の差だけ。kekka・cuta は 1e-12、終了年度 2039・最終カット率 1e-12
            （実測 2026-09-29: kekka 1e-14、cuta 0、最終カット率 0.8732176341806812）。
            `fix_bugs`（B11・J3 を直す）なら遺族基礎の給付費が +0.8%、最終カット率 3.4e-6 動く
"""
import os
import sys

import numpy as np
import pytest

from conftest import FAST
sys.path.insert(0, os.path.normpath(os.path.join(FAST, "..")))
import suuri_env                                            # noqa: E402

from kosoku.axis import YEARS                                # noqa: E402
from kosoku.io_port import read_year_rows                    # noqa: E402
from kosoku.policy import load_policy                        # noqa: E402
from kosoku.stages.s3_nat import run as NAT                  # noqa: E402
from kosoku.stages.s4_kiso_nenkin import run as RUN          # noqa: E402
from kosoku.stages.s4_kiso_nenkin.output import (to_port_csv, read_kekka, read_kyoshutukin,
                                                  read_cuta)  # noqa: E402

CASE = "3001"
S = suuri_env.suuri


def _need(path):
    if not os.path.exists(path):
        pytest.skip("無い: %s" % path)
    return path


def _paths():
    return dict(nat=_need(S("nat")), emp=_need(S("emp", "rslt", "u-rev", "kiso")),
                waku=_need(S("wakuc", "rslt", "ver_4_1", "rslt" + CASE)), bas=_need(S("bas")),
                econ=_need(S("emp", "data", "u-rev", "econ", "econ-%s.csv" % CASE)))


def _run(tmp, nat_out=None):
    p = _paths()
    _need(S("bas", "rslt", "kekka%s-%s-%s-%s-1120-000a.csv" % ((CASE,) * 4)))
    pol = load_policy()
    inp = RUN.read_inputs(pol, CASE, p["nat"], p["emp"], p["waku"], p["bas"], p["econ"], nat_out=nat_out)
    r = RUN.run(inp, CASE)
    paths = to_port_csv(r, CASE, tmp)
    return r, paths


@pytest.fixture(scope="module")
def from_port(tmp_path_factory):
    return _run(str(tmp_path_factory.mktemp("s4_port")))


@pytest.fixture(scope="module")
def from_fast(tmp_path_factory):
    p = _paths()
    pol = load_policy()
    ninp = NAT.read_inputs(pol, p["nat"], p["waku"], CASE, p["econ"])
    nr = NAT.run(ninp, CASE)
    return _run(str(tmp_path_factory.mktemp("s4_fast")), nat_out=nr.out)


PORT = {
    "kyoshutukin": S("bas", "data", "KYOSHUTUKIN%s-%s-%s-%s-000" % ((CASE,) * 4)),
    "cuta": S("bas", "rslt", "cuta-%s-%s-%s-%s-1120-000.csv" % ((CASE,) * 4)),
    "tumatumi": S("bas", "rslt", "TUMATUMI-%s-%s-%s-000-00.csv" % ((CASE,) * 3)),
    "kekka_a": S("bas", "rslt", "kekka%s-%s-%s-%s-1120-000a.csv" % ((CASE,) * 4)),
    "kekka_b": S("bas", "rslt", "kekka%s-%s-%s-%s-1120-000b.csv" % ((CASE,) * 4)),
}


def _worst(mine, port, cols=None):
    """{key: 配列} 同士の最大相対差（分母が小さい欄は絶対差）。"""
    worst, where = 0., None
    for k, p in port.items():
        m = mine[k]
        assert len(m) == len(p), (k, len(m), len(p))
        if cols is not None:
            m, p = m[cols], p[cols]
        d = np.abs(m - p)
        r = np.where(np.abs(p) > 1e-3, d / np.maximum(np.abs(p), 1e-300), d)
        i = int(np.argmax(r)) if r.size else 0
        if r.size and r[i] > worst:
            worst, where = float(r[i]), (k, i, m[i], p[i])
    return worst, where


# ---------------------------------------------------------------- 港の③を上流に

def test_終了年度と最終カット率(from_port):
    r, _ = from_port
    port = read_kekka(PORT["kekka_a"])
    assert r.sol.s_c_nendo == 2039
    assert r.sol.ok
    np.testing.assert_allclose(r.sol.saisyu_cut, 0.873217634180685, rtol=1e-9)
    np.testing.assert_allclose(r.sol.daitai, 31.941108, atol=5e-7)


def test_KYOSHUTUKINが移植版と一致(from_port):
    _, paths = from_port
    w, where = _worst(read_kyoshutukin(paths["kyoshutukin"]), read_kyoshutukin(PORT["kyoshutukin"]))
    assert w <= 1e-6, where


def test_cutaとTUMATUMIが移植版と一致(from_port):
    _, paths = from_port
    w, where = _worst(read_cuta(paths["cuta"]), read_cuta(PORT["cuta"]))
    assert w <= 1e-6, where
    w, where = _worst(read_year_rows(paths["tumatumi"], 2000), read_year_rows(PORT["tumatumi"], 2000))
    assert w <= 1e-6, where


@pytest.mark.parametrize("ab", ["a", "b"])
def test_kekkaの全ブロックが移植版と一致(from_port, ab):
    _, paths = from_port
    mine, port = read_kekka(paths["kekka_" + ab]), read_kekka(PORT["kekka_" + ab])
    assert list(mine) == list(port)
    for blk in port:
        w, where = _worst(mine[blk], port[blk])
        assert w <= 1e-6, "%s %s: %s" % (ab, blk, where)


def test_恒等式(from_port):
    """収入計・支出計 = 部分和、制度計 = Σ制度（`検証/数式編/verify_cc.py` と同じ検証A）。"""
    r, _ = from_port
    for ab in ("a", "b"):
        K = r.out.kekka[ab]["収支見通し"]
        shunyu = sum(K[c] for c in ("保険料収入（国年）", "保険料収入（付加年金）", "運用収入", "国庫（基礎年金）",
                                    "国庫（特別国庫）", "国庫（死亡一時金付加分）", "国庫（付加年金）",
                                    "国庫（旧法寡婦年金免除分）", "住宅融資債権", "妻積み",
                                    "こども子育て特別会計から繰入"))
        np.testing.assert_allclose(shunyu, K["収入合計"], rtol=1e-9)
        shishutu = sum(K[c] for c in ("死亡一時金納付分", "死亡一時金付加分", "新法寡婦年金",
                                      "旧法寡婦年金免除分以外", "旧法寡婦年金免除分", "付加年金",
                                      "基礎年金拠出金", "基礎年金拠出金（特別国庫）", "業務勘定への繰入"))
        np.testing.assert_allclose(shishutu, K["支出合計"], rtol=1e-9)
        G = r.out.kekka[ab]["基礎年金拠出金"]
        np.testing.assert_allclose(sum(G[s] for s in ("国年", "厚年", "国共", "地共", "私学")), G["合計"], rtol=1e-9)
        B = r.out.kekka[ab]["基礎年金給付費（新法＋旧法）"]
        np.testing.assert_allclose(sum(B["合計/" + s] for s in ("国年", "厚年", "国共", "地共", "私学")),
                                   B["合計/制度計"], rtol=1e-9)
        np.testing.assert_allclose(B["老齢/制度計"] + B["障害/制度計"] + B["遺族/制度計"], B["合計/制度計"], rtol=1e-9)


# ---------------------------------------------------------------- 高速版の③を上流に

def test_高速版の国年を上流にしても移植版と一致(from_fast):
    """既定の policy は③の癖（B11・J3）も原本どおりなので、高速版③を上流にしても④は移植版と
    丸め順の差まで一致する（実測 kekka 1e-14、cuta 0）。"""
    r, paths = from_fast
    assert r.sol.s_c_nendo == 2039
    np.testing.assert_allclose(r.sol.saisyu_cut, 0.873217634180685, rtol=1e-12)
    mine, port = read_kekka(paths["kekka_a"]), read_kekka(PORT["kekka_a"])
    for k in ("基礎年金拠出金", "基礎年金給付費（新法＋旧法）", "収支見通し"):
        w, where = _worst(mine[k], port[k])
        assert w <= 1e-12, (k, where)
    w, where = _worst(read_cuta(paths["cuta"]), read_cuta(PORT["cuta"]))
    assert w <= 1e-12, where
