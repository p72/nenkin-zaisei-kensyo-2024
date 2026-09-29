# -*- coding: utf-8 -*-
"""③国民年金の通し（フェーズ A の受け入れ）— 移植版③の出力との突き合わせ
==========================================================================
`work/suuri/rev2024` が無ければ飛ばす。ケース 3001（出生中位・死亡中位）。

比べるもの（`計画.md` 表A）
    KISONENKIN  1-1 老齢基礎 ／ 1-2 障害基礎 ／ 2-1 旧法老齢・5年 ／ 2-2 旧法障害 ／
                納付月数 ／ 年度間受給者数（障害）        → 相対 1e-6
    DOKUZI      独自給付 10列                            → 相対 1e-6
    KOKUKAITE   単年度改定率                             → 完全一致
    HIHO        被保険者数（種別 2・3・5・6）              → 相対 1e-6

既定の policy は原本の癖どおりなので、KISONENKIN は**全行**を 1e-6 で比べる。
`fix_bugs`（癖を意図どおりに直す overlay）で回したときは、移植版と**必ず違う**ところ
（`検証/原本の不具合.md`）を別の許容で見て、差の大きさを記録する:
    B11 遺族の 60〜64歳の枝の生命表の性別 → 1-3 遺族基礎（男）と年度間受給者数（遺族）
    J3  繰下げの移行措置の 2032年度以降の人数の添字 → 年度間受給者数（老齢）
どちらも台帳の実測（B11: 妻 +0.4〜2.0%、J3: 受給者数 +0.3〜1.4%）の範囲に収まること。
"""
import os
import sys

import numpy as np
import pytest

from conftest import FAST
sys.path.insert(0, os.path.normpath(os.path.join(FAST, "..")))
import suuri_env                                            # noqa: E402

from kosoku.axis import YEARS                                # noqa: E402
from kosoku.io_port import lines_of                          # noqa: E402
from kosoku.policy import load_policy                        # noqa: E402
from kosoku.stages.s3_nat import run as RUN                  # noqa: E402
from kosoku.stages.s3_nat.output import to_port_csv          # noqa: E402

CASE = "3001"
RTOL = 1e-6


def _need(path):
    if not os.path.exists(path):
        pytest.skip("無い: %s" % path)
    return path


def _run_fast(tmp_path_factory, *options):
    nat = _need(suuri_env.suuri("nat"))
    waku = _need(suuri_env.suuri("wakuc", "rslt", "ver_4_1", "rslt" + CASE))
    econ = _need(suuri_env.suuri("emp", "data", "u-rev", "econ", "econ-%s.csv" % CASE))
    _need(suuri_env.suuri("nat", "data", "KISONENKIN%s-%s-%s" % (CASE, CASE, CASE)))
    pol = load_policy(*options)
    inp = RUN.read_inputs(pol, nat, waku, CASE, econ)
    r = RUN.run(inp, CASE)
    out_dir = str(tmp_path_factory.mktemp("s3_out"))
    paths = to_port_csv(r.out, pol, CASE, out_dir)
    return r, paths


@pytest.fixture(scope="module")
def fast(tmp_path_factory):
    """既定の policy（原本の癖どおり）。"""
    return _run_fast(tmp_path_factory)


@pytest.fixture(scope="module")
def fast_fix(tmp_path_factory):
    """`fix_bugs`（B11・J3 などを意図どおりに直す）。"""
    return _run_fast(tmp_path_factory, "fix_bugs")


def _read_kisonenkin(path):
    """行を {(種類, 区分, 性, 年度, 年齢): 値} に。"""
    rows = {}
    for l in lines_of(path):
        f = [x.strip() for x in l.split(",")]
        if not f or not f[0].isdigit():
            continue
        if len(f) >= 7 and f[1] == "1":
            rows[("1", f[3] + "-" + f[4], int(f[5]), int(f[0]), int(f[2]))] = \
                np.array([float(x) for x in f[6:]])
        elif f[1] == "2":
            rows[("2", f[2], int(f[3]), int(f[0]), 0)] = np.array([float(x) for x in f[4:]])
        else:
            rows[("N", "noufu", 0, int(f[0]), 0)] = np.array([float(x) for x in f[1:]])
    return rows


def _worst(mine, port, select):
    """`select(key)` が真の行の最大相対差（分母が小さい欄は絶対差）。"""
    worst, where = 0., None
    n = 0
    for k, v in mine.items():
        if not select(k):
            continue
        p = port[k]
        assert len(v) == len(p), k
        d = np.abs(v - p)
        rel = np.where(np.abs(p) > 1e-3, d / np.maximum(np.abs(p), 1e-300), d)
        i = int(np.argmax(rel))
        if rel[i] > worst:
            worst, where = float(rel[i]), (k, v[i], p[i])
        n += 1
    assert n > 0, "比べる行が無い"
    return worst, where


def _kisonenkin_pair(run_result):
    _, paths = run_result
    port = _read_kisonenkin(suuri_env.suuri("nat", "data", "KISONENKIN%s-%s-%s" % (CASE, CASE, CASE)))
    mine = _read_kisonenkin(paths["kisonenkin"])
    assert set(mine) == set(port), "行の顔ぶれが違う"
    return mine, port


@pytest.fixture(scope="module")
def kisonenkin(fast):
    return _kisonenkin_pair(fast)


@pytest.fixture(scope="module")
def kisonenkin_fix(fast_fix):
    return _kisonenkin_pair(fast_fix)


@pytest.mark.parametrize("kind,typ", [("1", "1-1"), ("1", "1-2"), ("1", "1-3"), ("1", "2-1"),
                                      ("1", "2-2"), ("1", "2-3"), ("2", "1"), ("2", "2"),
                                      ("2", "3"), ("N", "noufu")])
def test_KISONENKINが移植版と一致(kisonenkin, kind, typ):
    """既定（原本の癖どおり）は遺族基礎・年度間受給者数（老齢・遺族）も含めて全行が一致。"""
    mine, port = kisonenkin
    w, where = _worst(mine, port, lambda k: k[0] == kind and k[1] == typ)
    assert w <= RTOL, "%s %s: 最大相対差 %.3e at %s" % (kind, typ, w, where)


def test_fix_bugsの遺族基礎の差はB11の実測の範囲(kisonenkin_fix):
    """1-3 遺族基礎（男）: 生命表を自分の性別で引くので移植版より大きい。"""
    mine, port = kisonenkin_fix
    w, where = _worst(mine, port, lambda k: k[0] == "1" and k[1] == "1-3" and k[2] == 1)
    assert 1e-4 < w <= 0.03, "B11 の効き方が想定外: %.3e at %s" % (w, where)
    # 女（夫）は 60〜64歳の枝の発生割合が 0 なので一致する
    w, _ = _worst(mine, port, lambda k: k[0] == "1" and k[1] == "1-3" and k[2] == 2)
    assert w <= RTOL
    w, where = _worst(mine, port, lambda k: k[0] == "2" and k[1] == "3")
    assert w <= 0.03, "年度間受給者数（遺族）: %.3e at %s" % (w, where)


def test_fix_bugsの年度間受給者数の老齢の差はJ3の実測の範囲(kisonenkin_fix):
    """2032年度以降だけ、移行措置の係数を 1 にした分だけ多い（+0.3〜1.5%）。"""
    mine, port = kisonenkin_fix
    w, _ = _worst(mine, port, lambda k: k[0] == "2" and k[1] == "1" and k[3] <= 2031)
    assert w <= RTOL, "2031年度までは一致するはず: %.3e" % w
    w, where = _worst(mine, port, lambda k: k[0] == "2" and k[1] == "1" and k[3] > 2031)
    assert 1e-4 < w <= 0.02, "J3 の効き方が想定外: %.3e at %s" % (w, where)


def test_fix_bugsは癖を直した移植版と全項目が一致(fast_fix):
    """`tools/nat_port_fixed.py OUTDIR` の出力（B11・J3 を直した移植版）があれば、
    `fix_bugs` の高速版と遺族・年度間受給者数も含めて全行を 1e-6 で比べる。`KOSOKU_NAT_PORTFIX=OUTDIR`。
    実測（2026-09-21、ケース 3001）: 84欄すべて 1e-9 以下、KOKUKAITE はバイト一致。"""
    root = os.environ.get("KOSOKU_NAT_PORTFIX")
    if not root:
        pytest.skip("KOSOKU_NAT_PORTFIX が無い（tools/nat_port_fixed.py で作る）")
    _, paths = fast_fix
    port = _read_kisonenkin(_need(os.path.join(root, "data", "KISONENKIN%s-%s-%s" % (CASE, CASE, CASE))))
    mine = _read_kisonenkin(paths["kisonenkin"])
    assert set(mine) == set(port)
    w, where = _worst(mine, port, lambda k: True)
    assert w <= RTOL, "最大相対差 %.3e at %s" % (w, where)
    a = lines_of(paths["kokukaite"])
    b = lines_of(os.path.join(root, "data", "KOKUKAITE-%s-%sE.csv" % (CASE, CASE)))
    assert a == b


def _read_table(path, ncol):
    out = {}
    for l in lines_of(path):
        f = [x.strip() for x in l.split(",")]
        if f and f[0].isdigit() and len(f) == ncol + 1:
            out[int(f[0])] = np.array([float(x) for x in f[1:]])
    return out


def test_DOKUZIが移植版と一致(fast):
    _, paths = fast
    port = _read_table(suuri_env.suuri("nat", "data", "DOKUZI%s-%s-%s.csv" % (CASE, CASE, CASE)), 10)
    mine = _read_table(paths["dokuzi"], 10)
    assert set(mine) == set(port)
    for y in sorted(port):
        np.testing.assert_allclose(mine[y], port[y], rtol=RTOL, atol=1e-6, err_msg="%d年度" % y)


def test_KOKUKAITEが移植版と完全一致(fast):
    _, paths = fast
    a = lines_of(paths["kokukaite"])
    b = lines_of(suuri_env.suuri("nat", "data", "KOKUKAITE-%s-%sE.csv" % (CASE, CASE)))
    assert a == b


def _hiho_block(path, title):
    L = lines_of(path)
    start = [i for i, l in enumerate(L) if l.strip() == title][0]
    out = {}
    for l in L[start + 2:]:
        f = [x.strip() for x in l.split(",")]
        if not f or not f[0].isdigit():
            break
        out[int(f[0])] = np.array([float(x) for x in f[1:]])
    return out


def test_被保険者数が移植版と一致(fast):
    """`HIHO` の種別ごとの表（年度間の計。被保険者数・納付・免除4段階・付加）。"""
    r, _ = fast
    p = _need(suuri_env.suuri("nat", "rslt", "HIHO%s-%s-%s.csv" % (CASE, CASE, CASE)))
    hiho = r.out.dokuzi["hiho"]
    for cls in RUN.CLASSES:
        port = _hiho_block(p, "被保険者数  種別=%d" % cls.port_shubetu)
        h = hiho[cls.name]
        for y, v in port.items():
            if y < 2021:
                continue
            yi = YEARS.i(y)
            got = np.array([h["kei"][yi], h["noufu"][yi], h["menjo"][yi, 1], h["menjo"][yi, 2],
                            h["menjo"][yi, 3], h["menjo"][yi, 4], h["fuka"][yi]])
            np.testing.assert_allclose(got, v, rtol=RTOL, atol=1e-6,
                                       err_msg="%s %d年度" % (cls.name, y))


def test_通しの時間(fast):
    """速度の目安（numba 無し）。目標は `計画.md` の ③ ≤ 1s（numba あり）。"""
    import time
    r, _ = fast
    inp = RUN.read_inputs(load_policy(), suuri_env.suuri("nat"),
                          suuri_env.suuri("wakuc", "rslt", "ver_4_1", "rslt" + CASE), CASE,
                          suuri_env.suuri("emp", "data", "u-rev", "econ", "econ-%s.csv" % CASE))
    t0 = time.perf_counter()
    RUN.run(inp, CASE)
    dt = time.perf_counter() - t0
    print("\n  ③ 通し %.2fs（numba 無し）" % dt)
    assert dt < 120.
