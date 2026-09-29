# -*- coding: utf-8 -*-
"""年度・年齢の漸化式カーネル
============================
規則は `jit.py` の docstring。フェーズ 0 では型を示す1本だけ
（`k_fund_recur`）。④⑤のカーネルは各フェーズで足す。
"""
import numpy as np

from .jit import njit

__all__ = ["k_fund_recur"]


@njit
def k_fund_recur(fund0, balance, out):
    """積立金 `out[k] = out[k-1] + balance[k]`、`out[0] = fund0 + balance[0]`。

    港: emp_shushi/shus_calc.py:shus_shushi
    仕様: §8.1
    """
    n = balance.shape[0]
    prev = fund0
    for k in range(n):
        prev = prev + balance[k]
        out[k] = prev
    return out
