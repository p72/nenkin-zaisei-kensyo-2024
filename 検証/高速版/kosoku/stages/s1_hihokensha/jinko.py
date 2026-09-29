# -*- coding: utf-8 -*-
"""①人口の整形（移植版 `setjinko.c`）
=====================================
1. 106 歳以上を 105 歳に寄せる
2. 有配偶率を `yuhaigy` より後の年度へ据え置く
3. 女を有配偶・無配偶に割る（§2.1）
4. 年央（10 月 1 日）→ 年度末（§2.2）。`nendomatsu` は労働力（`roudou.py`）も使う

港: hihokensha/setjinko.py:setjinko
仕様: §2.1、§2.2
"""
import numpy as np

from ...axis import AGES

__all__ = ["nendomatsu", "setjinko"]

NAGE = AGES.n


def nendomatsu(c, jw, lo, hi, base_i=0):
    """年央 `c[y, s, x]`（性 1〜3）→ 年度末（年度 0..NY−2、年齢 lo..hi）。性 4 は 2−3、性 0 は 1+2。

    その人が人口の基準年度に何歳だったか τ = x − (y − base_i) が正なら誕生月の分布 `jw` で
    重み付け（§2.2 の第 1 式）、そうでなければ 4 点の単純平均（第 2 式）。端の年齢は同じ年齢を
    2 回使う（lo 歳の「lo−1 歳」、hi 歳の「hi+1 歳」）。港の癖: 重み付きの lo 歳は最初の重みが
    1 − jw[τ]（他は 1 − jw[τ−1]）、hi 歳の最後の重みが jw[τ−1]（他は jw[τ]）。要素ごとの
    演算なので (年度, 年齢) をまとめる。
    仕様: §2.2
    港: hihokensha/setjinko.py:setjinko
    """
    ny = c.shape[0]
    m = np.zeros_like(c)
    y = np.arange(ny - 1)[:, None]
    x = np.arange(lo, hi + 1)[None, :]
    tau = x - (y - base_i)
    wgt = tau > 0
    t1 = np.clip(tau - 1, 0, NAGE - 1)
    t0 = np.clip(tau, 0, NAGE - 1)
    A = c[:-1, 1:4, lo:hi + 1]
    B = c[1:, 1:4, lo:hi + 1]
    Ap = np.concatenate([A[:, :, :1], c[:-1, 1:4, lo:hi]], axis=2)          # x−1（lo 歳は lo 歳）
    Bn = np.concatenate([c[1:, 1:4, lo + 1:hi + 1], B[:, :, -1:]], axis=2)  # x+1（hi 歳は hi 歳）
    for s in (1, 2, 3):
        w0 = 1. - jw[s][t1]
        w1 = jw[s][t0]
        w0p = w0.copy()
        w0p[:, 0] = 1. - jw[s][t0[:, 0]]
        w1l = w1.copy()
        w1l[:, -1] = jw[s][t1[:, -1]]
        k = s - 1
        weighted = (Ap[:, k] * w0p + A[:, k] * w1 + B[:, k] * w0 + Bn[:, k] * w1l) / 2.
        plain = (Ap[:, k] + A[:, k] + B[:, k] + Bn[:, k]) / 4.
        m[:-1, s, lo:hi + 1] = np.where(wgt, weighted, plain)
    m[:-1, 4, lo:hi + 1] = m[:-1, 2, lo:hi + 1] - m[:-1, 3, lo:hi + 1]
    m[:-1, 0, lo:hi + 1] = m[:-1, 1, lo:hi + 1] + m[:-1, 2, lo:hi + 1]
    return m


def setjinko(S, H):
    """港: hihokensha/setjinko.py:setjinko。仕様: §2.1、§2.2"""
    jc, jw, yr = H.jinko_c, H.jinko_wari, H.yuhaig_r
    top = 105
    # 1. 106 歳以上を 105 歳に寄せる（人数は非負なので > 0 の条件は要らない）
    jc[:, 1:3, top] += jc[:, 1:3, top + 1:].sum(axis=2)
    jc[:, 1:3, top + 1:] = 0.
    # 2. 有配偶率の据え置き
    i = S.hy.i(S.yuhaigy) + 1
    yr[i:, :top + 1] = yr[i - 1, :top + 1]
    # 3. 女を有配偶・無配偶に割る（§2.1）
    jc[:, 3, :top + 1] = jc[:, 2, :top + 1] * yr[:, :top + 1]
    jc[:, 4, :top + 1] = jc[:, 2, :top + 1] - jc[:, 3, :top + 1]
    jc[:, 0, :top + 1] = jc[:, 1, :top + 1] + jc[:, 2, :top + 1]
    # 4. 年央 → 年度末（§2.2）
    H.jinko_m[...] = nendomatsu(jc, jw, 0, top, S.hy.i(S.sjinkoy))
    H.sojinko_c[:, 0] = H.sojinko_c[:, 1] + H.sojinko_c[:, 2]
