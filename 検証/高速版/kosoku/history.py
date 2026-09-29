# -*- coding: utf-8 -*-
"""拠出履歴（計画 §J）— コホート × 年度の保険料の累積
=====================================================
②が持つ (年度, 性, 年齢) の被保険者数 `l`（①の外枠）と標準報酬 `bn`（基準年度価格。名目は `bn × ad`）、
⑤の保険料率から、**生年度ごと**に毎年の拠出額を積む。

    拠出[c, y] = Σ_性 l[y, 性, y − c] × bn[y, y − c, 性] × ad[y] × 料率[y]      （事業主負担込み。本人分はその半分）
    名目の累積   cum_nominal[c, y] = Σ_{y' ≤ y} 拠出[c, y']
    賃金評価の累積 cum_indexed[c, y] = Σ_{y' ≤ y} 拠出[c, y'] × ad[y] / ad[y']   （名目賃金上昇率で評価。NDC の仮想口座残高）

`ad` は②の賃金の累積指数（基準年度 = 1）。年度は `YEARS`、生年度は `ALL_COHORTS`（1880〜2125）。
履歴は②の外枠がある年度（基準年度の翌年度 2021〜）からしか無いので、それより前に加入していた生年度の
累積は**その年度からの分だけ**（`first_year` で分かる）。給付側と突き合わせるのは `benefit_formula.py`。
"""
from dataclasses import dataclass

import numpy as np

from .axis import YEARS, ALL_COHORTS

__all__ = ["History", "contribution_history", "by_cohort"]


@dataclass
class History:
    first_year: int                 # 履歴が始まる年度（それより前の拠出は無い）
    insured: np.ndarray             # (ALL_COHORTS.n, YEARS.n) 被保険者数（性の計）
    wages: np.ndarray               # 総報酬（名目）
    contrib: np.ndarray             # 拠出（名目、事業主込み）
    cum_nominal: np.ndarray
    cum_indexed: np.ndarray
    ad: np.ndarray                  # 賃金の累積指数（YEARS.n）

    def cohort(self, birth):
        return ALL_COHORTS.i(birth)


def by_cohort(a, year_axis=0, age_axis=1, age_lo=0):
    """(年度, 年齢) の配列 → (生年度, 年度)。`a[y, x]` を生年度 `y − x` の行へ散らす。"""
    a = np.moveaxis(np.asarray(a, dtype=np.float64), (year_axis, age_axis), (0, 1))
    ny, nx = a.shape[:2]
    out = np.zeros((ALL_COHORTS.n, YEARS.n) + a.shape[2:])
    ys = YEARS.labels()[:ny]
    for x in range(nx):
        c = ys - (x + age_lo) - ALL_COHORTS.first
        ok = (c >= 0) & (c < ALL_COHORTS.n)
        out[c[ok], np.arange(ny)[ok]] += a[ok, x]
    return out


def contribution_history(l, bn, ad, rate, first_year, sexes=(1, 2), ages=(15, 85)):
    """`l[y, s, x]` 被保険者数、`bn[y, x, s]` 標準報酬（基準年度価格、年額）、`ad[y]` 賃金の累積指数、
    `rate[y]` 保険料率。年度 `first_year` から積む。"""
    x0, x1 = ages
    ad = np.asarray(ad, dtype=np.float64)[:YEARS.n]                 # ②の ad は YEARS より 3 年長い
    i0 = YEARS.i(first_year)
    ins = np.zeros((YEARS.n, x1 - x0))
    wg = np.zeros((YEARS.n, x1 - x0))
    for s in sexes:
        ins[i0:] += l[i0:, s, x0:x1]
        wg[i0:] += l[i0:, s, x0:x1] * bn[i0:, x0:x1, s]
    wg *= ad[:, None]
    con = wg * rate[:, None]
    I = by_cohort(ins, age_lo=x0)
    W = by_cohort(wg, age_lo=x0)
    Cn = by_cohort(con, age_lo=x0)
    cum_n = np.cumsum(Cn, axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        inv_ad = np.where(ad > 0., 1. / ad, 0.)
    cum_i = np.cumsum(Cn * inv_ad[None, :], axis=1) * ad[None, :]
    return History(first_year, I, W, Cn, cum_n, cum_i, ad.copy())
