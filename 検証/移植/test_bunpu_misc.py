# -*- coding: utf-8 -*-
"""
⑥分布推計で使う細かい C/C++ の意味が移植版と一致するか
=======================================================
出力の1桁が変わる類のものを、その場の処理系に問い合わせて確かめる。

1. **`std::setprecision(15)` で `double` を流したときの文字列**
   `prog13.cpp` の出力はこれで決まる。C++ の既定の浮動小数形式は `%g`
   なので `%.15g` と同じはず、というのを実際に確かめる。
   inf / nan（対象者が0人のコホート）も含める。

2. **C の `%` は0方向に丸めた商の余り**
   `prog09.cpp:90` の `var006 % 10000` で、`var006` が負のときに効く。
   Python の `%` とは違う（`-1 % 10000` が -1 か 9999 か）。

3. **`int v = 0; v += double;` は1回ごとに切り捨てる**
   `prog13.cpp:49` の合計。
"""
import math
import os
import subprocess
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))

# モジュール名の衝突を避けるため、使うシステムを宣言する
# （`検証/移植/portpath.py` の解説を参照）
from portpath import select  # noqa: E402
SYSTEMS = ("clib", "bunpu")
select(*SYSTEMS)

from prog09 import _cmod                            # noqa: E402
from prog13 import _cdiv, _g15                      # noqa: E402

# 出力に出うる形をひととおり。末尾が丸めの境目になるものを混ぜる
G_CASES = [
    "0", "-0", "1", "100", "0.1", "0.3333333333333333",
    "90.2981492346258", "9.0982630184721", "0.140451935214323",
    "0.463135811687734", "30.4305", "78.3942593614786",
    "1e+20", "1e-20", "1.7976931348623157e308", "5e-324",
    "123456789012345.6", "1234567890123456.7", "0.000123456789012345678",
    "-12.5", "12345678901234567890",
]

# C の % で符号が問題になる組み合わせ
M_CASES = [(-1, 10000), (1, 10000), (20210101, 10000), (-20210101, 10000),
           (0, 10000), (9999, 10000), (-9999, 10000), (10000, 10000),
           (-7, 3), (7, -3), (-7, -3)]

# int に double を足していく列
I_CASES = [
    [3.7, 2.6],
    [0.0, 0.0, 0.0],
    [1.0, 2.0, 3.0],
    [0.5, 0.5, 0.5, 0.5],
    [101580.0, 10235.0, 158.0, 521.0],
    [-1.5, 3.9],
]


def find_cxx():
    for c in ("g++", "c++", "clang++"):
        if subprocess.run(["which", c], capture_output=True).returncode == 0:
            return c
    return None


@pytest.fixture(scope="session")
def probe():
    """その場の処理系に問い合わせた結果をまとめて返す。

    **`-O2` で建てる。** 原本の ⑥ の Makefile は `-Ofast` だが、
    `-ffast-math` は浮動小数の演算順の書き換えを許すので、
    IEEE 754 どおりの意味を問い合わせる目的には使えない
    （`検証/原本の不具合.md` G1）。
    """
    cxx = find_cxx()
    if cxx is None:
        pytest.skip("C++ コンパイラが無い")
    d = tempfile.mkdtemp(prefix="bunpu_misc_")
    exe = os.path.join(d, "probe")
    r = subprocess.run(
        [cxx, "-O2", "-w", "-o", exe,
         os.path.join(HERE, "harness_bunpu_misc.cpp")],
        capture_output=True, text=True)
    if r.returncode != 0:
        pytest.fail(f"ハーネスのビルドに失敗:\n{r.stderr[:2000]}")

    args = []
    for s in G_CASES:
        args += ["g", s]
    for a, b in M_CASES:
        args += ["m", str(a), str(b)]
    for xs in I_CASES:
        args += ["i", str(len(xs))] + [repr(x) for x in xs]

    r = subprocess.run([exe] + args, capture_output=True, text=True,
                       timeout=120)
    assert r.returncode == 0, r.stderr
    lines = r.stdout.splitlines()
    n = len(G_CASES) + len(M_CASES) + len(I_CASES)
    assert len(lines) == n, f"出力が {len(lines)} 行（期待 {n}）"
    k = 0
    g = {}
    for s in G_CASES:
        g[s] = lines[k]
        k += 1
    m = {}
    for a, b in M_CASES:
        m[(a, b)] = int(lines[k])
        k += 1
    acc = []
    for _ in I_CASES:
        acc.append(int(lines[k]))
        k += 1
    return g, m, acc


def test_setprecision15の出力が一致(probe):
    g, _, _ = probe
    bad = []
    for s, want in g.items():
        got = _g15(float(s))
        if got != want:
            bad.append(f"{s!r}: C++={want} Python={got}")
    assert not bad, "setprecision(15) が一致しない:\n  " + "\n  ".join(bad)


def test_inf_nanの出力():
    """0除算のときの出力。`func13a` は対象者0人だとここに来る。

    x86 では `0.0/0.0` の符号ビットが立つので `-nan` と出る（実測）。
    C++ コンパイラに問い合わせずに固定値で持っているのはここだけで、
    根拠は `検証/原本の不具合.md` G1 と同じ実測。
    """
    assert _g15(_cdiv(0.0, 0.0)) == "-nan"
    assert _g15(_cdiv(1.0, 0.0)) == "inf"
    assert _g15(_cdiv(-1.0, 0.0)) == "-inf"
    # 0 で割らない場合はふつうの割り算
    assert _cdiv(1.0, 4.0) == 0.25


def test_Cの剰余が一致(probe):
    _, m, _ = probe
    bad = []
    for (a, b), want in m.items():
        got = _cmod(a, b)
        if got != want:
            bad.append(f"{a} % {b}: C={want} Python={got}")
    assert not bad, "C の % と一致しない:\n  " + "\n  ".join(bad)
    # Python の % とは違うことを記録しておく
    assert (-1) % 10000 == 9999
    assert _cmod(-1, 10000) == -1


def test_intにdoubleを足す合計が一致(probe):
    _, _, acc = probe
    bad = []
    for xs, want in zip(I_CASES, acc):
        got = 0
        for x in xs:
            got = int(got + x)          # int += double と同じ
        if got != want:
            bad.append(f"{xs}: C++={want} Python={got}")
    assert not bad, "int += double が一致しない:\n  " + "\n  ".join(bad)


def test_func13cの合計も同じやり方():
    """`prog13.py` の `func13c` が上と同じ足し方をしているか。

    `arg13c5` は人数（`double`）なので整数値しか入らないが、足し方が
    違うと気付けるようにここで押さえておく。
    """
    import prog13
    src = open(prog13.__file__, encoding="utf-8").read()
    assert "total = int(total + arg13c5[i])" in src, (
        "func13c の合計が `int(total + …)` の形でなくなっている")


def test_g15が浮動小数点の刻みを取り違えない():
    """`-Ofast` が選んだ順と IEEE どおりの順で答えが違う例。

    `検証/原本の不具合.md` G1 の実例。移植版は **IEEE どおり**（`-O2`）に
    合わせる。
    """
    a, b = 101580.0, 112494.0
    assert _g15(a / b * 100.0) == "90.2981492346258"      # IEEE どおり
    assert _g15(a * (100.0 / b)) == "90.2981492346259"    # -Ofast が選んだ順
    assert not math.isclose(a / b * 100.0, a * (100.0 / b), rel_tol=0.0)
