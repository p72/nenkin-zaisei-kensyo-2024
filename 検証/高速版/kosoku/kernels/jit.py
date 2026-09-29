# -*- coding: utf-8 -*-
"""numba があれば `@njit`、無ければ恒等デコレータ
===================================================
規則（`計画.md`「numba と numpy の線引き」）:

- `kernels/` に置くのは (a) `y−1` や `x−1` を読む**本物の漸化式**で
  1段ごとの numpy 間接費が支配的になるもの、(b) 解法の反復の内側、だけ
- カーネルは float64 の素の配列だけを受け取る（構造体 dtype は入れない）
- 各カーネルに `_ref.py` の純 numpy 双子を置き、`tests/test_kernels_ref.py`
  が rtol 1e-12 で一致を見る（numba あり／なしの両方で）

`KOSOKU_NOJIT=1` で numba があっても使わない（テスト用）。
"""
import os

__all__ = ["njit", "HAVE_NUMBA", "ENABLED"]

try:
    import numba as _numba
    HAVE_NUMBA = True
except ImportError:                      # pragma: no cover - 環境依存
    _numba = None
    HAVE_NUMBA = False

ENABLED = HAVE_NUMBA and os.environ.get("KOSOKU_NOJIT", "") not in ("1", "true")


def njit(*args, **kwargs):
    """`@njit` / `@njit(cache=True)` の両方の書き方を受ける。"""
    if args and callable(args[0]) and not kwargs:
        fn = args[0]
        return _numba.njit(cache=True)(fn) if ENABLED else fn

    def deco(fn):
        if ENABLED:
            kwargs.setdefault("cache", True)
            return _numba.njit(**kwargs)(fn)
        return fn
    return deco
