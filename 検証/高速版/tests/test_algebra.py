# -*- coding: utf-8 -*-
"""`kosoku.algebra` が `nat/str_op.py`（移植版＝原本）と rtol 1e-12 で一致すること
================================================================================
移植版の8つの構造体 dtype から `Layout` を作り、乱数入力で8演算を突き合わせる。
高速版は丸めの順序を約束しないので、ビット一致ではなく rtol 1e-12。

移植版は読み取り専用で import する（`portpath.select("clib", "nat")`）。
"""
import numpy as np
import pytest

from portpath import select
select("clib", "nat")

import str_op as S                                        # noqa: E402
from setconst import TOKUTEI_NENDO, TOKUTEI_TUKI          # noqa: E402

from kosoku import algebra as A                           # noqa: E402

DTYPES = {n: v for n, v in vars(S).items() if isinstance(v, np.dtype) and v.names}
RTOL = 1e-12


def _layout(name):
    dt = DTYPES[name]
    return A.layout_from_dtype(name, dt,
                               no_kaitei=S._NO_KAITEI.get(dt, ()),
                               kaitei2=S._KAITEI2.get(dt, ()),
                               keep=S._KEEP.get(dt, ()))


def _rand(dt, seed, positive=False):
    """移植版の構造体1個と、同じ値の高速版の1次元配列。"""
    n = dt.itemsize // 8
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(n) * 1e5
    if positive:
        v = np.abs(v) + 1.
    a = np.zeros((), dtype=dt)
    a.reshape(1).view(np.float64)[:] = v
    return a, v.copy()


def _flat(x):
    return np.asarray(x).reshape(1).view(np.float64).copy()


def _close(got, want, what):
    np.testing.assert_allclose(got, want, rtol=RTOL, atol=0., err_msg=what)


@pytest.mark.parametrize("name", sorted(DTYPES))
def test_scalar_add_multiply(name):
    dt = DTYPES[name]
    a, av = _rand(dt, 1)
    b, bv = _rand(dt, 2)
    for s in (0.5, 1.0, -3.25, 1e-3):
        _close(A.scalar(s, av), _flat(S.scalar(s, a)), "%s scalar %r" % (name, s))
    _close(A.add(av, bv), _flat(S.add(a, b)), "%s add" % name)
    if dt not in (S.HIHOKENSHA, S.GONEN, S.ICHIJIKIN):
        _close(A.multiply(av, bv), _flat(S.multiply(a, b)), "%s multiply" % name)


@pytest.mark.parametrize("name", sorted(n for n in DTYPES if DTYPES[n] != S.HIHOKENSHA))
def test_nendokan(name):
    dt = DTYPES[name]
    L = _layout(name)
    a, av = _rand(dt, 3)
    b, bv = _rand(dt, 4)
    for k1, k2 in ((1.0, 1.0), (0.997, 1.0404), (1.02, 0.98)):
        if dt in S._KAITEI2:
            want = S.nendokan(a, b, k1, k2)
            got = A.nendokan(L, av, bv, k1, k2)
        else:
            want = S.nendokan(a, b, k1)
            got = A.nendokan(L, av, bv, k1)
        _close(got, _flat(want), "%s nendokan %r" % (name, (k1, k2)))


@pytest.mark.parametrize("name", sorted(n for n in DTYPES
                                        if DTYPES[n] not in (S.HIHOKENSHA, S.KAFU)))
def test_nendokan_64(name):
    dt = DTYPES[name]
    L = _layout(name)
    a, av = _rand(dt, 5)
    b, bv = _rand(dt, 6)
    c, cv = _rand(dt, 7)
    for k in (1.0, 0.997, 1.0404):
        _close(A.nendokan_64(L, av, bv, cv, k), _flat(S.nendokan_64(a, b, c, k)),
               "%s nendokan_64 %r" % (name, k))


@pytest.mark.parametrize("name", sorted(n for n in DTYPES
                                        if DTYPES[n] not in (S.HIHOKENSHA, S.ICHIJIKIN)))
def test_adjustbenefit(name):
    dt = DTYPES[name]
    L = _layout(name)
    a, av = _rand(dt, 8)
    for s in (0.9, 1.0, 0.5):
        _close(A.adjustbenefit(L, s, av), _flat(S.adjustbenefit(s, a)),
               "%s adjustbenefit %r" % (name, s))


def test_average_by_ninzu():
    dt = S.HIHOKENSHA
    a, av = _rand(dt, 9, positive=True)
    _close(A.average_by_ninzu(av), _flat(S.average_by_ninzu(a)), "average_by_ninzu")
    a["ninzu"] = 0.
    av[0] = 0.
    _close(A.average_by_ninzu(av), _flat(S.average_by_ninzu(a)), "average_by_ninzu 人数0")


@pytest.mark.parametrize("nendo", [TOKUTEI_NENDO - 5, TOKUTEI_NENDO - 1, TOKUTEI_NENDO,
                                   TOKUTEI_NENDO + 1, 2024])
def test_scalar_splitはscalar_2と一致(nendo):
    """③ `scalar_2`（国庫負担 1/3 → 1/2 の切替年度の按分）の一般化。"""
    dt = S.HIHOKENSHA
    L = _layout("HIHOKENSHA")
    a, av = _rand(dt, 10)
    old = tuple("menjo[%d][1]" % d for d in range(5))
    new = tuple("menjo[%d][2]" % d for d in range(5))
    tot = tuple("menjo[%d][0]" % d for d in range(5))
    if nendo < TOKUTEI_NENDO:
        frac = 0.
    elif nendo == TOKUTEI_NENDO:
        frac = (16 - TOKUTEI_TUKI) / 12.
    else:
        frac = 1.
    for s in (0.5, 1.0, 2.0):
        _close(A.scalar_split(L, s, av, old, new, tot, frac),
               _flat(S.scalar_2(s, a, nendo)), "scalar_split %d %r" % (nendo, s))


def test_layoutの検査():
    with pytest.raises(ValueError):
        A.Layout("x", ("kihon", "ninzu"))
    with pytest.raises(ValueError):
        A.Layout("x", ("ninzu", "kihon"), keep=("fuka",))
    L = A.Layout("x", ("ninzu", "kihon", "kakyu"), kaitei2=("kakyu",))
    with pytest.raises(ValueError):
        L.nendokan_weights(1.0)          # 加給の改定率が要る
    assert L.zeros(3, 2).shape == (3, 2, 3)


def test_多次元でも同じ():
    """最後の次元がスロット。前の次元（年度×年齢）はまとめて処理できる。"""
    L = _layout("ROREI")
    dt = S.ROREI
    rng = np.random.default_rng(11)
    x = rng.standard_normal((4, 3, L.n)) * 1e4
    y = rng.standard_normal((4, 3, L.n)) * 1e4
    got = A.nendokan(L, x, y, 1.01)
    for i in range(4):
        for j in range(3):
            a = np.zeros((), dtype=dt)
            a.reshape(1).view(np.float64)[:] = x[i, j]
            b = np.zeros((), dtype=dt)
            b.reshape(1).view(np.float64)[:] = y[i, j]
            _close(got[i, j], _flat(S.nendokan(a, b, 1.01)), "多次元 (%d,%d)" % (i, j))
