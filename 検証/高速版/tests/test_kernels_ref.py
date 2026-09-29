# -*- coding: utf-8 -*-
"""各カーネルが純 numpy の双子（`kernels/_ref.py`）と rtol 1e-12 で一致する。
numba があれば JIT 版、無ければ素の Python で同じテストが回る。"""
import numpy as np

from kosoku.kernels import jit
from kosoku.kernels.recur import k_fund_recur
from kosoku.kernels._ref import fund_recur_ref


def test_fund_recur():
    rng = np.random.default_rng(0)
    for n in (1, 5, 126):
        b = rng.standard_normal(n) * 1e12
        out = np.empty(n)
        k_fund_recur(2.5e14, b, out)
        np.testing.assert_allclose(out, fund_recur_ref(2.5e14, b), rtol=1e-12)


def test_jitの状態が読める():
    assert isinstance(jit.HAVE_NUMBA, bool)
    assert isinstance(jit.ENABLED, bool)
    if not jit.HAVE_NUMBA:
        assert not jit.ENABLED
