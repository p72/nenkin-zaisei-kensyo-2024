# -*- coding: utf-8 -*-
"""
cnum.py と原本の C をビット単位で突き合わせる
=============================================
harness_cnum.c をその場でビルドして走らせ、round()・nround()・atof() の
結果を %a（16進浮動小数＝無損失）で比較する。1ビットでも違えば落ちる。

境界値は手で並べ、そのうえで再現可能な乱数で総当たりする。
"""
import math
import os
import random
import struct
import subprocess
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))

# モジュール名の衝突を避けるため、使うシステムを宣言する
# （`検証/移植/portpath.py` の解説を参照）
from portpath import select  # noqa: E402
SYSTEMS = ("emp_shushi",)
select(*SYSTEMS)

import cnum  # noqa: E402


# --------------------------------------------------------------------------
# ハーネスのビルド（セッション中1回）
# --------------------------------------------------------------------------
@pytest.fixture(scope="session")
def harness():
    cc = None
    for cand in ("cc", "gcc", "clang"):
        if subprocess.run(["which", cand], capture_output=True).returncode == 0:
            cc = cand
            break
    if cc is None:
        pytest.skip("C コンパイラが無いので差分テストを飛ばす")

    exe = os.path.join(tempfile.mkdtemp(prefix="cnum_"), "harness")
    r = subprocess.run(
        [cc, "-O0", "-o", exe, os.path.join(HERE, "harness_cnum.c"), "-lm"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        pytest.skip(f"ハーネスのビルドに失敗: {r.stderr[:300]}")
    return exe


def run_c(harness, lines):
    """ハーネスに問い合わせて double のリストを返す。"""
    r = subprocess.run(
        [harness], input="\n".join(lines) + "\n",
        capture_output=True, text=True, timeout=120,
    )
    assert r.returncode == 0, r.stderr
    out = [ln for ln in r.stdout.splitlines() if ln != ""]
    assert len(out) == len(lines), f"入力 {len(lines)} 行に対し出力 {len(out)} 行"
    return [float.fromhex(s) for s in out]


def bits(x):
    """double のビット列。NaN の符号やゼロの符号も区別する。"""
    return struct.pack(">d", x).hex()


def same(a, b):
    if math.isnan(a) and math.isnan(b):
        return True
    return bits(a) == bits(b)


# --------------------------------------------------------------------------
# round()
# --------------------------------------------------------------------------
# 半数ちょうど、その直上・直下、負数、大きい値、ゼロの符号。
ROUND_EDGE = [
    0.0, -0.0,
    0.5, -0.5, 1.5, -1.5, 2.5, -2.5, 3.5, -3.5,
    0.49999999999999994,    # 0.5 の直下。floor(x+0.5) だと 1 になってしまう値
    -0.49999999999999994,
    0.5000000000000001, -0.5000000000000001,
    1.0, -1.0, 1.4999999999999998, 2.0000000000000004,
    4503599627370495.5,     # 2^52 - 0.5
    4503599627370496.0,     # 2^52。これ以上は整数しか表せない
    9007199254740993.0,
    1e15 + 0.5, -1e15 - 0.5,
    1e300, -1e300, 1e-300,
]


def test_round_境界値(harness):
    lines = [f"round {float(x).hex()}" for x in ROUND_EDGE]
    got_c = run_c(harness, lines)
    for x, c in zip(ROUND_EDGE, got_c):
        p = cnum.c_round(x)
        assert same(p, c), f"round({x!r}): C={c!r} Python={p!r}"


def test_round_乱数(harness):
    rng = random.Random(20260920)
    vals = []
    # 半数の近くを重点的に。丸めの境界はそこにしか無い。
    for _ in range(3000):
        n = rng.randint(-10000, 10000)
        frac = rng.choice([
            0.5, -0.5,
            0.5 + rng.uniform(-1e-15, 1e-15),
            rng.uniform(0.0, 1.0),
            rng.uniform(-1.0, 0.0),
        ])
        vals.append(n + frac)
    # 桁の広い値も混ぜる
    for _ in range(1000):
        vals.append(rng.uniform(-1e18, 1e18))
        vals.append(rng.uniform(-1.0, 1.0) * 10 ** rng.randint(-20, 20))

    got_c = run_c(harness, [f"round {float(x).hex()}" for x in vals])
    for x, c in zip(vals, got_c):
        p = cnum.c_round(x)
        assert same(p, c), f"round({x!r}): C={c!r} Python={p!r}"


def test_round_半数の隣を1ulp刻みで総当たり(harness):
    """見つかったバグは全部「半数ちょうどの隣の double」に潜んでいた。
    そこだけ 1 ulp 刻みで舐める。nextafter で真の隣の値を作る。"""
    vals = []
    for k in list(range(-20, 21)) + [1000, -1000, 2 ** 40, -(2 ** 40),
                                     2 ** 52 - 1, -(2 ** 52 - 1)]:
        for half in (k + 0.5, k - 0.5):
            v = half
            for _ in range(3):
                v = math.nextafter(v, -math.inf)
            for _ in range(7):
                vals.append(v)
                v = math.nextafter(v, math.inf)
    # 0 のまわり（負のゼロが出る領域）
    v = math.nextafter(0.0, -math.inf)
    for _ in range(40):
        vals.append(v)
        v = math.nextafter(v, -math.inf)
    vals += [0.0, -0.0]

    got_c = run_c(harness, [f"round {float(x).hex()}" for x in vals])
    for x, c in zip(vals, got_c):
        p = cnum.c_round(x)
        assert same(p, c), f"round({x!r} = {float(x).hex()}): C={c!r} Python={p!r}"


def test_nround_半数の隣を1ulp刻みで総当たり(harness):
    """nround は 10^n 倍してから丸めるので、境界は 0.5/10^n の近くに来る。"""
    cases = []
    for n in (0, 1, 2, 3, 5, 12):
        scale = 10.0 ** n
        for k in list(range(-12, 13)) + [777, -777]:
            v = (k + 0.5) / scale
            for _ in range(3):
                v = math.nextafter(v, -math.inf)
            for _ in range(7):
                cases.append((v, n))
                v = math.nextafter(v, math.inf)
    # 負のゼロが出る領域（桁を大きく落とす場合）
    for n in (-3, -8):
        for k in range(1, 15):
            cases.append((-float(k) * 1e-6, n))
            cases.append((float(k) * 1e-6, n))

    got_c = run_c(harness, [f"nround {float(x).hex()} {n}" for x, n in cases])
    for (x, n), c in zip(cases, got_c):
        p = cnum.nround(x, n)
        assert same(p, c), f"nround({x!r} = {float(x).hex()}, {n}): C={c!r} Python={p!r}"


def test_round_はPythonの組込みと違う():
    """組込み round() を使うと落ちることを明示しておく（退行防止）。"""
    assert cnum.c_round(2.5) == 3.0 and round(2.5) == 2
    assert cnum.c_round(-2.5) == -3.0 and round(-2.5) == -2
    assert cnum.c_round(0.5) == 1.0 and round(0.5) == 0
    # floor(x + 0.5) を使うと落ちる値
    assert cnum.c_round(0.49999999999999994) == 0.0
    assert math.floor(0.49999999999999994 + 0.5) == 1


# --------------------------------------------------------------------------
# nround()
# --------------------------------------------------------------------------
def test_nround_原本が使う桁(harness):
    """原本が実際に呼んでいる桁だけは特に厚く見る。
    econ.c は 3、rdfl.c は 12 と 5、shus_out.c は 0。"""
    rng = random.Random(4649)
    cases = []
    for n in (0, 3, 5, 12):
        for _ in range(1200):
            style = rng.randint(0, 3)
            if style == 0:
                x = rng.uniform(-2.0, 2.0)
            elif style == 1:
                x = rng.uniform(-1.0, 1.0) * 10 ** rng.randint(-6, 6)
            elif style == 2:
                # 丸めの境界ちょうど（x*10^n が半整数になる値）
                k = rng.randint(-100000, 100000)
                x = (k + 0.5) / (10.0 ** n)
            else:
                x = rng.uniform(-1e9, 1e9)
            cases.append((x, n))

    got_c = run_c(harness, [f"nround {float(x).hex()} {n}" for x, n in cases])
    for (x, n), c in zip(cases, got_c):
        p = cnum.nround(x, n)
        assert same(p, c), f"nround({x!r}, {n}): C={c!r} Python={p!r}"


def test_nround_桁を広く(harness):
    rng = random.Random(1129)
    cases = []
    for n in range(-8, 16):
        for _ in range(200):
            cases.append((rng.uniform(-1.0, 1.0) * 10 ** rng.randint(-10, 10), n))
    got_c = run_c(harness, [f"nround {float(x).hex()} {n}" for x, n in cases])
    for (x, n), c in zip(cases, got_c):
        p = cnum.nround(x, n)
        assert same(p, c), f"nround({x!r}, {n}): C={c!r} Python={p!r}"


# --------------------------------------------------------------------------
# atof()
# --------------------------------------------------------------------------
ATOF_CASES = [
    "0", "1", "-1", "1.5", "-1.5", "0.0", "-0.0",
    "", " ", "  \t ",                       # 原本は末尾カンマの行でこれを渡す
    "abc", "-", "+", ".", "+.", "-.",       # 数値として読めない → 0.0
    "1.", ".5", "-.5", "+.5",
    "1e3", "1E3", "1e+3", "1e-3", "1.5e10", "-1.5e-10",
    "1e", "1e+", "1.5e",                    # 指数部が欠けている
    "  42  ", "42abc", "42.5xyz",           # 読める所まで
    "0.1", "0.2", "0.3", "1e308", "1e-308", "1e309", "1e-400",
    "123456789012345678901234567890",
    "0.30000000000000004",
    "780900", "5.481E-3", "0.926", "0.994", "0.996",   # 原本に出てくる定数
    "0x10", "0x1p4",                        # 16進浮動小数
    "inf", "-inf", "nan", "INF", "NaN",
]


def test_atof(harness):
    got_c = run_c(harness, [f"atof {s}" for s in ATOF_CASES])
    for s, c in zip(ATOF_CASES, got_c):
        p = cnum.c_atof(s)
        assert same(p, c), f"atof({s!r}): C={c!r} Python={p!r}"


def test_atof_乱数(harness):
    rng = random.Random(3939)
    cases = []
    for _ in range(1500):
        x = rng.uniform(-1.0, 1.0) * 10 ** rng.randint(-20, 20)
        cases.append(repr(x))
        cases.append(f"{x:.17g}")
        cases.append(f"{x:.6f}")
    # 実データに出てくる形（符号・小数点・空欄）
    for _ in range(300):
        cases.append(f"{rng.randint(-10**9, 10**9)}")
        cases.append(f"{rng.uniform(0, 1):.12f}")

    got_c = run_c(harness, [f"atof {s}" for s in cases])
    for s, c in zip(cases, got_c):
        p = cnum.c_atof(s)
        assert same(p, c), f"atof({s!r}): C={c!r} Python={p!r}"


# --------------------------------------------------------------------------
# 整数演算
# --------------------------------------------------------------------------
def test_c_idiv_は床除算と違う():
    """C の int 除算は 0 方向、Python の // は床方向。"""
    assert cnum.c_idiv(7, 2) == 3 and 7 // 2 == 3
    assert cnum.c_idiv(-7, 2) == -3 and -7 // 2 == -4
    assert cnum.c_idiv(7, -2) == -3 and 7 // -2 == -4
    assert cnum.c_idiv(-7, -2) == 3
    for a in range(-50, 51):
        for b in list(range(-9, 0)) + list(range(1, 10)):
            assert cnum.c_idiv(a, b) == int(a / b), (a, b)


def test_c_trunc():
    for x in (2.7, -2.7, 0.0, -0.0, 1e15 + 0.5, -1e15 - 0.5):
        assert cnum.c_trunc(x) == int(x)


# --------------------------------------------------------------------------
# printf 書式
# --------------------------------------------------------------------------
def test_fmt_は偶数丸め():
    """printf("%.<n>f") は round() とは別物。混同していないことを確かめる。"""
    # 2進で厳密に 0.5 になる値は偶数側へ
    assert cnum.fmt(0.5, 0) == "0"
    assert cnum.fmt(1.5, 0) == "2"
    assert cnum.fmt(2.5, 0) == "2"
    assert cnum.fmt(3.5, 0) == "4"
    # 一方 nround(x, 0) は 0 から遠い方へ
    assert cnum.nround(0.5, 0) == 1.0
    assert cnum.nround(2.5, 0) == 3.0


def test_fmt_はCのprintfと一致(harness):
    """%.<n>f は C と同じか。ハーネスを介さず、C の printf を直に叩いて確かめる。"""
    cc = None
    for cand in ("cc", "gcc", "clang"):
        if subprocess.run(["which", cand], capture_output=True).returncode == 0:
            cc = cand
            break
    if cc is None:
        pytest.skip("C コンパイラが無い")

    rng = random.Random(555)
    cases = []
    for _ in range(800):
        style = rng.randint(0, 2)
        if style == 0:
            x = rng.uniform(-1000, 1000)
        elif style == 1:
            x = (rng.randint(-100000, 100000) + 0.5) / 10 ** rng.randint(0, 4)
        else:
            x = rng.uniform(-1, 1) * 10 ** rng.randint(-8, 12)
        cases.append((x, rng.choice([0, 1, 2, 3, 6, 12, 15])))

    src = os.path.join(tempfile.mkdtemp(prefix="cfmt_"), "f.c")
    with open(src, "w") as f:
        f.write("#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>\n"
                "int main(void){char l[256];double x;int n;\n"
                "while(fgets(l,sizeof l,stdin)){sscanf(l,\"%lf %d\",&x,&n);"
                "printf(\"%.*f\\n\", n, x);}return 0;}\n")
    exe = src[:-2]
    r = subprocess.run([cc, "-O0", "-o", exe, src], capture_output=True, text=True)
    if r.returncode != 0:
        pytest.skip(f"ビルド失敗: {r.stderr[:200]}")

    inp = "\n".join(f"{float(x).hex()} {n}" for x, n in cases) + "\n"
    r = subprocess.run([exe], input=inp, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    out = r.stdout.splitlines()
    assert len(out) == len(cases)
    for (x, n), c in zip(cases, out):
        p = cnum.fmt(x, n)
        assert p == c, f'printf("%.{n}f", {x!r}): C={c!r} Python={p!r}'
