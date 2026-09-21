# -*- coding: utf-8 -*-
"""
libc の関数。⑤で検証済みの実装をそのまま使い回す
=================================================
⑥分布推計も `round()`（`<cmath>` 経由）を使う。これは C99 の
**0から遠い方向への丸め**で、Python 組み込みの `round()`（偶数丸め）とは
違う。⑤の移植で実装して `検証/移植/test_cnum.py` で C と突き合わせて
あるので、**同じものを2つ持たない**ようにここから読み込む。

    c_round(x)   C99 の round()。0.5 は 0 から遠い方へ。-0.0 を保つ
    c_trunc(x)   C99 の trunc()
    c_idiv(a, b) C の整数除算（0方向へ丸める）
    c_atof(s)    C の atof()。読めなければ 0.0（④で検証済み）
    cdiv(a, b)   0 で割っても落ちない double 除算（同）

`round()` の戻り値を int に入れると C では0方向への切り捨てが入るが、
`c_round` の結果はもともと整数値なので `int(c_round(x))` でよい。

`sys.path` はいじらない。⑤（`emp_shushi/`）と⑥（`bunpu/`）には
`main.py` や `setconst.py` のように**同じ名前のモジュール**があるので、
`sys.path` に両方を入れると取り違える。ファイルの場所を指定して直接
読み込む。
"""
import importlib.util
import math
import os
import re

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(_HERE, *rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_cnum = _load("_emp_cnum", ("emp_shushi", "cnum.py"))

c_round = _cnum.c_round
c_trunc = _cnum.c_trunc
c_idiv = _cnum.c_idiv


# ---- strtod / atof -------------------------------------------------
# C の `strtod` が読む表記。どのシステムも同じ libc を呼ぶので同じ文法。
# ④の移植で実装して `検証/移植/test_kiso_num.py` で C と突き合わせた
# ものをここに移した（④の `cnum.py` はここから読み込む）。
_HEXF = re.compile(
    r"[+-]?0[xX](?:[0-9a-fA-F]+(?:\.[0-9a-fA-F]*)?|\.[0-9a-fA-F]+)"
    r"(?:[pP][+-]?[0-9]+)?")
_DECF = re.compile(
    r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
_INFF = re.compile(r"[+-]?[iI][nN][fF](?:[iI][nN][iI][tT][yY])?")
_NANF = re.compile(r"[+-]?[nN][aA][nN](?:\([0-9a-zA-Z_]*\))?")
_WS = " \t\n\v\f\r"


def c_atof(s):
    """C の `atof`。読めなければ 0.0（エラーにしない）。"""
    i = 0
    n = len(s)
    while i < n and s[i] in _WS:
        i += 1
    m = _HEXF.match(s, i)
    if m:
        try:
            return float.fromhex(m.group(0))
        except (ValueError, OverflowError):
            return 0.0
    m = _DECF.match(s, i)
    if m:
        try:
            return float(m.group(0))
        except (ValueError, OverflowError):
            return 0.0
    m = _INFF.match(s, i)
    if m:
        return -math.inf if m.group(0)[:1] == "-" else math.inf
    m = _NANF.match(s, i)
    if m:
        return -math.nan if m.group(0)[:1] == "-" else math.nan
    return 0.0


def cdiv(a, b):
    """C の `double / double`。**0 で割っても落ちない。**

    ④にも分母のゼロを確かめていない割り算がある
    （`tumatumi_cal_jisseki.c:217` の `SanteiTaishou[SUM][...][SUM]` など）。
    NumPy の `float64` 同士なら C と同じふるまいになるので、
    配列から取り出した値は `float()` に落とさずそのまま使う。
    素の Python の float を割るところだけこれを通す。
    """
    if b == 0.0:
        if a == 0.0:
            return -math.nan
        return math.copysign(math.inf, a) * math.copysign(1.0, b)
    return a / b


__all__ = ["c_round", "c_trunc", "c_idiv", "c_atof", "cdiv"]
