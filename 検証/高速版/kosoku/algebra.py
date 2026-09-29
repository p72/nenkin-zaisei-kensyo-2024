# -*- coding: utf-8 -*-
"""給付代数 — `nat/str_op.py` の8演算を欄リスト駆動にしたもの
==============================================================
移植版③は8つの構造体（`hihokensha` `rorei` … `ichijikin`）に同じ8演算を
型ごとに多重定義している。高速版は「欄の並び」を `Layout` として持ち、
**どの給付でも同じ関数**で扱う。配列は最後の次元がスロット
（`shape = (..., layout.n)`、スロット0 は必ず `ninzu`）。

演算の意味は移植版と同じ（`tests/test_algebra.py` が乱数入力で rtol 1e-12
の一致を確かめる）が、**丸めの順序は約束しない**。

    scalar(s, x)                 全スロットに s を掛ける
    add(a, b)                    全スロットを足す
    multiply(a, b)               全スロットを要素ごとに掛ける
    nendokan(L, a, b, k1, k2)    年度間の額。支払遅れ2か月、付加は改定しない、加給は k2
    nendokan_64(L, a, b, c, k)   64歳の年（当年度末が2区分）。人数は3つ足して2で割る
    adjustbenefit(L, s, x)       マクロ経済スライドを年金額の欄だけに掛ける
    average_by_ninzu(x)          人数で割る（人数 0 なら 0）
    scalar_split(L, s, x, ...)   ③ `scalar_2` の一般化。国庫負担割合の切替年度の按分

港: nat/str_op.py:scalar, add, multiply, nendokan, nendokan_64, adjustbenefit,
    average_by_ninzu, scalar_2
仕様: §5.1（年度末と年度間）、§5.6（マクロ経済スライドの当て方）
"""
from dataclasses import dataclass

import numpy as np

__all__ = ["Layout", "SHIHARAIOKURE", "scalar", "add", "multiply", "nendokan",
           "nendokan_64", "adjustbenefit", "average_by_ninzu", "scalar_split",
           "layout_from_dtype"]

# 年金は2か月遅れで支払う（str_op.c:7）
SHIHARAIOKURE = 2


@dataclass(frozen=True)
class Layout:
    """スロットの並び。`fields[0]` は必ず `"ninzu"`。

    `no_kaitei`: 年度間で改定率を掛けない欄（付加年金）
    `kaitei2`:   年度間で2つ目の改定率を当てる欄（加給）
    `keep`:      マクロ経済スライドで素通しする欄（付加年金。人数は常に素通し）
    """
    name: str
    fields: tuple
    no_kaitei: tuple = ()
    kaitei2: tuple = ()
    keep: tuple = ()

    def __post_init__(self):
        if not self.fields or self.fields[0] != "ninzu":
            raise ValueError("%s: fields[0] は ninzu でなければならない" % self.name)
        for grp in (self.no_kaitei, self.kaitei2, self.keep):
            for f in grp:
                if f not in self.fields:
                    raise ValueError("%s: 欄 %s が無い" % (self.name, f))

    @property
    def n(self):
        return len(self.fields)

    def i(self, name):
        return self.fields.index(name)

    def slots(self, names):
        return np.array([self.fields.index(f) for f in names], dtype=np.intp)

    def zeros(self, *shape):
        return np.zeros(tuple(shape) + (self.n,), dtype=np.float64)

    # 年度間の重み。スロットごとに normal / no_kaitei / kaitei2 の3種類
    def nendokan_weights(self, kaiteiritu, kaiteiritu2=None):
        w = np.full(self.n, SHIHARAIOKURE + 6. * kaiteiritu, dtype=np.float64)
        if self.no_kaitei:
            w[self.slots(self.no_kaitei)] = SHIHARAIOKURE + 6.
        if self.kaitei2:
            if kaiteiritu2 is None:
                raise ValueError("%s: 加給の改定率が要る" % self.name)
            w[self.slots(self.kaitei2)] = SHIHARAIOKURE + 6. * kaiteiritu2
        w[0] = 0.
        return w


def layout_from_dtype(name, dt, no_kaitei=(), kaitei2=(), keep=()):
    """移植版の構造体 dtype から `Layout` を作る（テストと移行用）。

    `menjo` のような (5, 3) の欄は `menjo[d][k]` の名前で15スロットに展開する
    （C の並びどおり行優先）。
    """
    fields = []
    for f in dt.names:
        sub = dt.fields[f][0]
        if sub.shape:
            for idx in np.ndindex(*sub.shape):
                fields.append("%s[%s]" % (f, "][".join(str(i) for i in idx)))
        else:
            fields.append(f)

    def expand(names):
        out = []
        for nm in names:
            out.extend([f for f in fields if f == nm or f.startswith(nm + "[")])
        return tuple(out)
    return Layout(name, tuple(fields), expand(no_kaitei), expand(kaitei2), expand(keep))


def _last(x):
    return np.asarray(x, dtype=np.float64)


def scalar(s, x):
    """全スロットに `s` を掛ける（人数も掛ける）。"""
    return _last(x) * s


def add(a, b):
    return _last(a) + _last(b)


def multiply(a, b):
    return _last(a) * _last(b)


def nendokan(layout, a, b, kaiteiritu, kaiteiritu2=None):
    """年度間の額。`a` が前年度末、`b` が当年度末。

        額   = (a × (2 + 6 × 改定率) + b × (6 − 2)) / 12
        人数 = (a + b) / 2
    """
    a, b = _last(a), _last(b)
    w1 = layout.nendokan_weights(kaiteiritu, kaiteiritu2)
    out = (a * w1 + b * (6. - SHIHARAIOKURE)) / 12.
    out[..., 0] = (a[..., 0] + b[..., 0]) / 2.
    return out


def nendokan_64(layout, a, b, c, kaiteiritu):
    """当年度末が2つの区分（`b` と `c`）にまたがる年。人数は3つ足して2で割る。"""
    a, b, c = _last(a), _last(b), _last(c)
    w1 = layout.nendokan_weights(kaiteiritu, kaiteiritu)
    out = (a * w1 + (b + c) * (6. - SHIHARAIOKURE)) / 12.
    out[..., 0] = (a[..., 0] + b[..., 0] + c[..., 0]) / 2.
    return out


def adjustbenefit(layout, s, x):
    """マクロ経済スライドの調整率を年金額の欄だけに掛ける。人数と付加は素通し。"""
    x = _last(x)
    out = x * s
    keep = layout.slots(("ninzu",) + tuple(layout.keep))
    out[..., keep] = x[..., keep]
    return out


def average_by_ninzu(x):
    """各欄を人数で割る。人数が 0 以下なら 0。人数の欄はそのまま。"""
    x = _last(x)
    n = x[..., 0:1]
    pos = n > 0.
    out = np.divide(x, n, out=np.zeros_like(x), where=pos)
    out[..., 0] = x[..., 0]
    return out


def scalar_split(layout, s, x, cols_old, cols_new, cols_sum, frac_new):
    """③ `scalar_2` の一般化。制度の切替年度に旧・新の欄を按分する。

    `cols_old` `cols_new` `cols_sum` は同じ長さの欄名の列（段階ごと）。
    `frac_new` は新制度の月数割合（切替前の年度は 0、切替後は 1、
    切替年度は (16 − 月) / 12 など）。まず全スロットに `s` を掛け、
    旧の欄 × (1 − frac_new)、新の欄 × frac_new、計 = 旧 + 新。
    """
    x = _last(x)
    out = x * s
    io, i_n, i_s = layout.slots(cols_old), layout.slots(cols_new), layout.slots(cols_sum)
    out[..., io] = out[..., io] * (1. - frac_new)
    out[..., i_n] = out[..., i_n] * frac_new
    out[..., i_s] = out[..., io] + out[..., i_n]
    return out
