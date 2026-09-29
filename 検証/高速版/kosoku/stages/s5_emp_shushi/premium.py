# -*- coding: utf-8 -*-
"""保険料率のスケジュールとモデル世帯（移植版 `shus.c:init_premium` `shus_calc.c:shus_smodel`）
==============================================================================================
保険料率（`policy.shushi.hokenryoritu`）
    率[y] = min(cap, base + step × (y − base_year))        制度ごと。2009年度から持つ
    年度内平均[y] = (w0 × 率[y−1] + w1 × 率[y]) / 12        w は制度ごとの月数の重み

港の `Prema` の並びは 1 厚年, 2 国共済, 3 地共済, 4 私学, 5 第3種（坑内員・船員）。
港の docstring は 4 を「旧農林」、5 を「私学」と書いているが、使われ方
（`Cc[4][1] = An[4] × Premb[4]`、`An[1][3] × (Premb[5] − Premb[1])`）から
4 が私学、5 が第3種の上乗せ分。高速版は名前で持つ（`sig`, `kofu`）。

モデル世帯（`policy.shushi.model`）
    賃金 W[2024]（5 区分）、可処分所得 Kw = round(W × 0.813)
    比例部分 Mhirei = round(W × 5.481/1000 × 0.926 × 40) / 0.994 / 0.996
    基礎 Mkiso = 136,000 × 0.985 / 0.994 / 0.996
    以降 W は名目賃金で、Kw は W と手取り割合 (0.91 − 厚年率/2) の変化で延ばす。
    `round` は C99（0 から遠い方へ）。所得代替率の分母なので法定の丸めとして残す

港: emp_shushi/shus.py:init_premium
港: emp_shushi/shus_calc.py:shus_smodel
港: emp_shushi/cnum.py:c_round
仕様: §13（保険料率）、§9（所得代替率のモデル世帯）
"""
from dataclasses import dataclass
import math

import numpy as np

from ...axis import YEARS
from .inputs import SYSTEMS, KOFU

__all__ = ["c_round", "Premium", "premium_rates", "Model", "model_household"]


def c_round(x):
    """C99 の round()（0 から遠い方へ）。港: emp_shushi/cnum.py:c_round"""
    t = float(math.trunc(x))
    d = x - t
    if d >= 0.5:
        return t + 1.
    if d <= -0.5:
        return t - 1.
    return t


@dataclass
class Premium:
    """`rate[name][y]` 保険料率、`avg[name][y]` 年度内平均。name は制度名と `kofu`。"""
    rate: dict
    avg: dict


def premium_rates(pol, ks, override=None):
    """`override={"from": 年度, "rate": r}` で、その年度から全制度（第3種も）の率を r に置き換える
    （均衡の解法で料率を動かすとき。`kosoku/balance.py`）。"""
    sched = pol.get("shushi.hokenryoritu")
    weights = pol.get("shushi.premb_weights")
    stty = YEARS.i(pol.get("shushi.years.stty"))
    ys = YEARS.labels()
    rate, avg = {}, {}
    for name in SYSTEMS + (KOFU,):
        s = sched[name]
        r = np.minimum(s["cap"], s["base"] + s["step"] * (ys - s["base_year"]))
        r[:stty] = 0.
        if override is not None:
            r[YEARS.i(int(override["from"])):] = float(override["rate"])
        rate[name] = r
        w0, w1 = weights[name]
        a = YEARS.zeros()
        i0 = YEARS.i(ks) + 1
        a[i0:] = (w0 * r[i0 - 1:-1] + w1 * r[i0:]) / 12.
        avg[name] = a
    return Premium(rate, avg)


@dataclass
class Model:
    """モデル世帯。`w[y, i]` 賃金、`kw[y, i]` 可処分所得、`mhirei[y, i]` 比例部分、`mkiso[y]` 基礎。"""
    w: np.ndarray
    kw: np.ndarray
    mhirei: np.ndarray
    mkiso: np.ndarray


def model_household(pol, h, prema_kou, ke):
    """`h[y]` 名目賃金上昇率、`prema_kou[y]` 厚年の保険料率。"""
    M = pol.get("shushi.model")
    i0 = YEARS.i(M["mdlk"])
    ie = YEARS.i(ke)
    n = len(M["w_2024"])
    w = np.zeros((YEARS.n, n)); kw = np.zeros((YEARS.n, n)); mh = np.zeros((YEARS.n, n))
    mk = YEARS.zeros()
    k23, k24 = M["kaitei_2023"], M["kaitei_2024"]
    w[i0] = M["w_2024"]
    mk[i0] = M["kiso_2024"] * M["mihanei"] / k23 / k24
    for i in range(n):
        kw[i0, i] = c_round(w[i0, i] * M["kasho"])
        mh[i0, i] = c_round(w[i0, i] * M["hirei_joritu"] * M["hirei_hosei"] * 40.) / k23 / k24
    kb = M["kashobun"]
    for y in range(i0 + 1, ie + 1):
        w[y] = (1. + h[y - 1]) * w[y - 1]
        tedori = (kb - prema_kou[y - 1] / 2.) / (kb - prema_kou[y - 2] / 2.)
        kw[y] = kw[y - 1] * w[y] / w[y - 1] * tedori
        mh[y] = mh[y - 1] * kw[y] / kw[y - 1]
        mk[y] = mk[y - 1] * (1. + h[y - 1]) * tedori
    return Model(w, kw, mh, mk)
