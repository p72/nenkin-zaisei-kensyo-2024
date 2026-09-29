# -*- coding: utf-8 -*-
"""各カーネルの純 numpy 双子。`tests/test_kernels_ref.py` が rtol 1e-12 で
`recur.py` と突き合わせる。numba があっても無くても、こちらは常に素の Python。"""
import numpy as np

__all__ = ["fund_recur_ref"]


def fund_recur_ref(fund0, balance):
    """積立金の漸化式 `fund[k] = fund[k-1] + balance[k]`（k = 1..）。

    港: emp_shushi/shus_calc.py:shus_shushi（`Cc[20,k] = Cc[20,k-1] + Cc[19,k]`）
    仕様: §8.1
    """
    out = np.empty_like(balance)
    out[0] = fund0 + balance[0]
    out[1:] = fund0 + np.cumsum(balance)[1:]
    return out
