# -*- coding: utf-8 -*-
"""年度中の受給者数・年金額の年齢階級別の集計（移植版 `shke.c` 相当）
====================================================================
年度末の人数・年金額（`*_Nendomatu`）に**支給率**を掛けて「年度中に支給される
ぶん」にし、年齢階級（63歳以下をひとまとめ、64歳〜115歳は1歳刻み）に足し上げる。

    受給[y, m, …] = Σ_{x ∈ 階級 m} 支給率[y, x] · 年度末[y, x, …]

年齢階級の添字 `m`: 0 = 計（後で作る）、1 = 63歳以下、2 = 64歳 … 53 = 115歳
（港: `UNDER_63 − NENREI_SUM` = 1、`nenrei − NENREI_SUM`）。

老齢の繰下げ75歳化の移行措置（`Waribikiritu`）は5コホート × 5繰下げ年齢だけに
人数・年金額の係数を掛ける。2032年度以降の人数の係数は、既定では原本どおり 2023年度の値
（台帳 J3。`kokunen.quirks.j3_waribiki_ninzu_2023`）、`fix_bugs` では 2031年度の値（= 1）。

港: nat/shke.py:shke
仕様: §5.2.1（Waribikiritu）、§12.4（集計の出力）
"""
import numpy as np

from ...algebra import adjustbenefit
from ...axis import AGES
from .layouts import ROREI, MENJO_DANKAI, KOKKO_KUBUN

__all__ = ["AGE_CLASS_N", "age_class", "sum_by_class", "apply_waribiki", "menjo_totals"]

AGE_CLASS_N = 54           # 0 計、1 63歳以下、2〜53 = 64〜115歳
UNDER = 63


def age_class(ages):
    """年齢 → 階級の添字。63歳以下は 1。"""
    ages = np.asarray(ages)
    return np.where(ages <= UNDER, 1, ages - UNDER + 1)


def sum_by_class(values, ages):
    """`values[k, …]`（年齢 `ages[k]` の並び）を階級ごとに足す → (AGE_CLASS_N, …)。
    足す順は年齢の昇順（縮約。順序は約束しない）。"""
    out = np.zeros((AGE_CLASS_N,) + values.shape[1:])
    np.add.at(out, age_class(ages), values)
    return out


def apply_waribiki(shikyu, year, kuriage_ages, cohort_year_of_age, waribiki_n, waribiki_b,
                   first_year, last_year, ninzu_after_k=None):
    """繰下げ75歳化の移行措置。`shikyu[n, j, :]`（年齢 n・繰下げ年齢 j）のうち
    生年度 = first_year − 繰下げ年齢 の1マスだけに係数を掛ける。

    `waribiki_n[j_idx, k]` 人数の係数、`waribiki_b[j_idx, k]` 年金額の係数
    （k = 年度 − first_year。first_year〜last_year の10年）。last_year より後は
    最後の係数。ただし `ninzu_after_k` を渡すと、人数だけその添字を使う（原本どおりの J3 は 1）。
    """
    n_k = waribiki_n.shape[1]
    for ji, j_age in enumerate(kuriage_ages):
        age = year - (first_year - j_age)              # このコホートの当年度の年齢
        n = cohort_year_of_age(age)
        if n is None:
            continue
        if year < first_year:
            continue
        k = min(year - first_year, n_k - 1)
        kn = ninzu_after_k if (ninzu_after_k is not None and year > last_year) else k
        j = j_age - 60
        shikyu[n, j, 0] *= waribiki_n[ji, kn]
        shikyu[n, j] = adjustbenefit(ROREI, waribiki_b[ji, k], shikyu[n, j])
    return shikyu


def menjo_totals(arr, layout):
    """免除の「計」（段階の計・国庫区分の計・両方）を埋める。`arr[..., slot]`。"""
    for d in range(1, MENJO_DANKAI):
        for k in range(1, KOKKO_KUBUN):
            v = arr[..., layout.i("menjo[%d][%d]" % (d, k))]
            arr[..., layout.i("menjo[0][%d]" % k)] += v
            arr[..., layout.i("menjo[%d][0]" % d)] += v
            arr[..., layout.i("menjo[0][0]")] += v
    return arr
