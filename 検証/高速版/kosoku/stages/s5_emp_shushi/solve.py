# -*- coding: utf-8 -*-
"""厚生年金の調整終了年度の解法（移植版 `shus_calc.c:shus_calc8` 相当）
========================================================================
名目下限つきの毎年の調整率 `rh` と、持ち越し（キャリーオーバー）の特別調整率
`tokutyo` を年度・年齢で作り、厚年の累積調整率 `Sh`（港の `Escutrrh`）を解く。

    dcutr[y, x] = max(0, スライド調整率[y])
                  持ち越しあり（2018年度〜）: (1 + dcutr) / tokutyo[y−1, x−1] − 1
    rh[y, x]    = 1 + max(0, min(dcutr, 比例改定率[y, dx] − 1))    dx = max(67, x)（名目下限）
    tokutyo[y, x] = rh / (1 + dcutr)（2023・2024 年度は 1。キャリーオーバー廃止なら 2025 年度〜 1）
    実績: 2014年度（76歳以下）、2023・2024年度の rh は `policy.shushi.slide_actuals`
    Sh[y, x] = Sh[y−1, x−1] / rh[y, x]      調整中の年度（コホートごとに持ち越す）
             = Sh[y−1, x−1]                 調整の終わった年度

有限均衡の条件 f = 積立金[2119] − 支出[2120] × Ca ≥ 0（制度計）。
  1. 基準年度の翌年度から1年ずつ調整を延ばし、f ≥ 0 になる最初の年度 kn を探す
     （2024年度より前では止めない）
  2. kn 年度の率を、前年度の率（rrh_min）と kn まで調整した率（rrh_max）の間で
     割線法 14 回 → 二分法（合計 62 回まで）で詰める。収束判定は
     |積立金[2119]/支出[2120] − Ca| < 0.5e-13

港: emp_shushi/shus_calc.py:shus_calc8
仕様: §8.1（均衡条件）、§8.2〜8.3（求解）、§5.7（名目下限とキャリーオーバー）
"""
from dataclasses import dataclass

import numpy as np

from ...axis import YEARS, AGES
from .inputs import AGE_LO, AGE_HI
from .shushi import C, nendokan, balance, fund_margin

__all__ = ["Slide", "rh_tokutyo", "shift_forward", "Solution", "solve"]


@dataclass
class Slide:
    rh: np.ndarray            # (YEARS.n, AGES.n) 毎年の名目下限つき調整率
    tokutyo: np.ndarray       # (YEARS.n, AGES.n) 特別調整率（持ち越し分）


def _nround(x, n):
    d = 10.0 ** n
    v = x * d
    return np.floor(abs(v) + 0.5) * np.sign(v) / d


def rh_tokutyo(pol, scutrk1, krb, ke, carry=1, d_macro=0):
    """`scutrk1[YEARS.n]` 毎年のスライド調整率、`krb` 比例の改定率。`carry=0` でキャリーオーバー廃止、
    `d_macro=1` で名目下限の撤廃（2025年度〜）。"""
    Yn = pol.get("shushi.years")
    act = pol.get("shushi.slide_actuals")
    actuals = {int(k): v for k, v in act.items() if str(k).isdigit()}
    i_first = YEARS.i(Yn["slide_first"])
    i_km = YEARS.i(Yn["kmakuro_yr"])
    i_km2 = YEARS.i(Yn["kmakuro_yr2"])
    i_dm = YEARS.i(Yn["dmakuro_yr"])
    ie = YEARS.i(ke)
    x60 = AGES.i(60)
    xs = np.arange(x60, AGES.i(AGE_HI) + 1)
    dxs = np.maximum(xs, AGES.i(67))
    rh = np.ones((YEARS.n, AGES.n))
    tok = np.ones((YEARS.n, AGES.n))
    reset = set(YEARS.i(int(y)) for y in act["tokutyo_reset"])
    for i in range(i_first, ie + 1):
        y = YEARS.label(i)
        a = actuals.get(y)
        dcutr = np.full(xs.shape, max(0., float(scutrk1[i])))
        if (i >= i_km and d_macro != 1) or (d_macro == 1 and i <= i_dm):
            dcutr = (1. + dcutr) / tok[i - 1, np.maximum(x60, xs - 1)] - 1.
        if d_macro != 1 or i < i_dm:
            r = 1. + np.maximum(0., np.minimum(dcutr, krb[i, dxs] - 1.))
            if isinstance(a, dict):                        # 2014年度: 特例水準の解消分
                r = np.where(xs <= AGES.i(a["max_age"]),
                             _nround(a["numer"] / a["denom"], a["digits"]), r)
        else:
            r = 1. + np.maximum(0., dcutr)
        if i >= i_km:
            t = r / (1. + dcutr)
            if i in reset:
                t = np.ones_like(t)
            if (t < 0.).any() or (t > 1.).any():
                raise ValueError("特別調整率が [0, 1] の外: 年度 %d" % y)
            tok[i, xs] = t
        if a is not None and not isinstance(a, dict):      # 2023・2024年度: 実績の改定率
            r = np.full(xs.shape, 1. / a)
        if carry == 0 and i >= i_km2:
            tok[i, xs] = 1.
        rh[i, xs] = r
    return Slide(rh, tok)


def shift_forward(S, i_from, ie):
    """`i_from + 1`〜`ie` の率を前年度からコホートでずらす（調整の終わった年度）。63 歳は据え置き。"""
    x63 = AGES.i(AGE_LO)
    for i in range(i_from + 1, ie + 1):
        S[i, x63] = S[i - 1, x63]
        S[i, x63 + 1:] = S[i - 1, x63:-1]


@dataclass
class Solution:
    kn: int                    # 調整終了年度（厚年）
    Sh: np.ndarray             # 厚年の累積調整率
    St: np.ndarray             # 国年の累積調整率（調整期間の一致なら厚年と同じ）
    slide: Slide
    n_scan: int
    n_iter: int
    ok: bool
    r: float                   # 最後の割線法の位置
    margin: float              # 積立金[kend−1] − 支出[kend] × Ca（合わせる条件の余裕）
    rule: str = "current"      # 均衡の解法（`kosoku/balance.py`）
    premium_rate: float = None  # 料率を動かす解法の答え（`premium_from` 年度からの率）
    rates: np.ndarray = None    # 賦課方式の毎年の料率 (NSYS, YEARS.n)


def solve(pol, Cc, E, ben, scutrk1, St0, kra, krb, ke, carry=1, d_macro=0, touitu=False, margin=None):
    """`Cc` は保険料・固定項目を入れた台帳（書き換える）。`ben` 年齢別の給付、`St0` 国年の累積調整率。
    `margin(Cc)` を渡すと合わせる条件を差し替える（`kosoku/balance.py`。既定は有限均衡 `fund_margin`。
    収束は |margin| < tol × 支出[終期]）。"""
    Yn = pol.get("shushi.years")
    bal = pol.get("shushi.balance")
    ca = bal["ca"]
    tol = bal["tol"]
    n_sec = bal["secant_iters"]
    n_max = bal["max_iters"]
    kijun = YEARS.i(Yn["kijun"])
    ie = YEARS.i(ke)
    kend = YEARS.i(Yn["kend"])
    k_jis = YEARS.i(Yn["k_jisseki"])
    x63 = AGES.i(AGE_LO)
    nendohosei = pol.get("shushi.nendohosei")

    slide = rh_tokutyo(pol, scutrk1, krb, ke, carry, d_macro)
    rh = slide.rh
    Sh = np.ones((YEARS.n, AGES.n))
    St = St0.copy()

    def evaluate(i_from):
        nendokan(Cc, ben, Sh, St, kra, krb, i_from, ie, nendohosei, touitu)
        balance(Cc, E, kijun, max(i_from, kijun + 1), ie)
        return fund_margin(Cc, kend, ca) if margin is None else margin(Cc)

    f1 = evaluate(kijun)
    f0 = 0.
    kn = kend + 1
    found = False
    n_scan = 0
    i = kijun + 1
    while i < ie and not found:
        Sh[i, x63] = Sh[i - 1, x63] / rh[i, x63]
        Sh[i, x63 + 1:] = Sh[i - 1, x63:-1] / rh[i, x63 + 1:]
        shift_forward(Sh, i, ie)
        f0 = f1
        f1 = evaluate(i)
        n_scan += 1
        if f1 >= 0. and i >= k_jis:
            kn = i
            found = True
        i += 1
    if not found:
        return Solution(YEARS.label(min(kn, YEARS.n - 1)), Sh, St, slide, n_scan, 0, False, 0., f1)

    rrh_max = Sh[kn, x63:].copy()
    rrh_min = np.concatenate([[Sh[kn - 1, x63]], Sh[kn - 1, x63:-1]])
    n = 0
    r0, r1, r = 0., 1., 1.
    f = f1
    ok = kn <= k_jis
    while n < n_max and not ok:
        if n < n_sec:
            r = r1 - f1 * (r1 - r0) / (f1 - f0)
        else:
            r = (r1 + r0) / 2.
        Sh[kn, x63:] = rrh_min * (1. - r) + rrh_max * r
        shift_forward(Sh, kn, ie)
        f = evaluate(kn)
        if margin is None:
            ratio = Cc[:, C.TUMITATE, kend - 1].sum() / Cc[:, C.SHISHUTU, kend].sum()
            conv = abs(ratio - ca) < tol
        else:
            conv = abs(f) < tol * abs(Cc[:, C.SHISHUTU, ie].sum())
        if conv:
            ok = True
        elif f * f0 > 0.:
            r0, f0 = r, f
        else:
            r1, f1 = r, f
        n += 1
    if touitu:
        St = Sh.copy()
    return Solution(YEARS.label(kn), Sh, St, slide, n_scan, n, ok, r, f)
