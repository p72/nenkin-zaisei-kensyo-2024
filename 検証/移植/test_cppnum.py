# -*- coding: utf-8 -*-
"""
cppnum.py が `std::stoi` / `std::stod` と一致するか
===================================================
⑥分布推計は CSV の値をこの2つで数値にする（`prog05.cpp` ほか）。
⑤が使う C の `atof` とは**ふるまいが違う**ので分けてある。

    C の atof()        読めなければ 0.0（エラーにしない）
    C++ の std::stod() 読めなければ std::invalid_argument を投げる

原本は例外を捕まえていないので、読めない値があればその場で落ちる。
移植でも同じ所で例外にする必要がある。**どこで落ちるかも挙動の一部**。

値を埋め込まずに、その場の libstdc++ をコンパイルして問い合わせる。
"""
import math
import os
import struct
import subprocess
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))

# モジュール名の衝突を避けるため、使うシステムを宣言する
# （`検証/移植/portpath.py` の解説を参照）
from portpath import select  # noqa: E402
SYSTEMS = ("clib", "emp_shushi")
select(*SYSTEMS)

from cppnum import (CppInvalidArgument, CppOutOfRange, stod,  # noqa: E402
                    stoi)

# 符号・空白・途中で止まる形・範囲外・16進・inf/nan を混ぜる
CASES = [
    "0", "1", "12", "-12", "+12", " 12", "  -3  ", "12abc", "abc", "",
    " ", "\t", "0x10", "0X1F", "0x", "1.5", "1.5xyz", "-1.5", "1e5",
    "1E5", "1e+5", "1e-5", "1e400", "1e-400", "1e308", "1e309",
    "2147483647", "2147483648", "-2147483648", "-2147483649",
    "99999999999999999999", "0.0", "-0.0", "+0.0",
    "inf", "-inf", "INF", "infinity", "nan", "NaN", "-nan",
    ".5", "-.5", "5.", "1,5", "1.2.3", "1e", "1e+", "+", "-", ".",
    "0.1", "0.30000000000000004", "780900", "5.481E-3",
    "  0x1p4", "9007199254740993", "4.9406564584124654e-324",
    "2.2250738585072014e-308", "1.7976931348623157e308",
    "1.7976931348623159e308",
]


def find_cxx():
    for c in ("g++", "c++", "clang++"):
        if subprocess.run(["which", c], capture_output=True).returncode == 0:
            return c
    return None


@pytest.fixture(scope="session")
def probe():
    """その場の libstdc++ に問い合わせた結果。"""
    cxx = find_cxx()
    if cxx is None:
        pytest.skip("C++ コンパイラが無い")

    d = tempfile.mkdtemp(prefix="cppnum_")
    exe = os.path.join(d, "probe")
    r = subprocess.run(
        [cxx, "-O2", "-w", "-o", exe, os.path.join(HERE, "harness_cppnum.cpp")],
        capture_output=True, text=True)
    if r.returncode != 0:
        pytest.fail(f"ハーネスのビルドに失敗:\n{r.stderr[:2000]}")

    r = subprocess.run([exe] + CASES, capture_output=True, text=True,
                       timeout=120)
    assert r.returncode == 0, r.stderr
    lines = r.stdout.splitlines()
    assert len(lines) == 2 * len(CASES), (
        f"出力が {len(lines)} 行（期待 {2 * len(CASES)}）")

    out = {}
    for k, s in enumerate(CASES):
        li, ld = lines[2 * k], lines[2 * k + 1]
        assert li.startswith("i ") and ld.startswith("d "), (li, ld)
        out[s] = (li[2:].strip(), ld[2:].strip())
    return out


def bits(x):
    return struct.pack(">d", float(x)).hex()


def test_stoiが原本と一致(probe):
    bad = []
    for s, (ci, _) in probe.items():
        try:
            got = str(stoi(s))
        except CppInvalidArgument:
            got = "invalid"
        except CppOutOfRange:
            got = "range"
        if got != ci:
            bad.append(f"stoi({s!r}): C++={ci} Python={got}")
    assert not bad, "libstdc++ と一致しない:\n  " + "\n  ".join(bad)


def test_stodが原本と一致(probe):
    bad = []
    for s, (_, cd) in probe.items():
        try:
            v = stod(s)
            got = ("nan" if math.isnan(v)
                   else ("inf" if v == math.inf
                         else ("-inf" if v == -math.inf else None)))
        except CppInvalidArgument:
            got = "invalid"
        except CppOutOfRange:
            got = "range"
        else:
            if got is None:
                # 数値どうしは %a（無損失）で比べる
                if cd in ("invalid", "range", "inf", "-inf", "nan", "-nan"):
                    bad.append(f"stod({s!r}): C++={cd} Python={v!r}")
                    continue
                if bits(v) != bits(float.fromhex(cd)):
                    bad.append(f"stod({s!r}): C++={cd} Python={float(v).hex()}")
                continue
        # 例外・inf・nan の側
        cd_norm = cd
        if cd in ("-nan",):
            cd_norm = "nan"            # NaN の符号は区別しない
        if got != cd_norm:
            bad.append(f"stod({s!r}): C++={cd} Python={got}")
    assert not bad, "libstdc++ と一致しない:\n  " + "\n  ".join(bad)


def test_atofとは違うことを記録():
    """C の atof とは違う、という記録。混同すると⑥で落ち方が変わる。

    ⑤は atof（読めなければ 0.0）、⑥は stod（投げる）。
    """
    # `SYSTEMS` に emp_shushi を入れてあるので素に読み込める
    from cnum import c_atof

    # 読めない文字列
    assert c_atof("abc") == 0.0
    with pytest.raises(CppInvalidArgument):
        stod("abc")

    # 空文字列
    assert c_atof("") == 0.0
    with pytest.raises(CppInvalidArgument):
        stod("")

    # 範囲外は atof なら inf、stod なら例外
    assert c_atof("1e400") == math.inf
    with pytest.raises(CppOutOfRange):
        stod("1e400")


def test_範囲外の判定(probe):
    """`1e-400` が out_of_range になる（0 に潰れるので）ことを押さえる。

    `0` や `0.0` は正当な 0 なので投げてはいけない。
    """
    with pytest.raises(CppOutOfRange):
        stod("1e-400")
    assert stod("0") == 0.0
    assert stod("0.0") == 0.0
    assert bits(stod("-0.0")) == bits(-0.0)
