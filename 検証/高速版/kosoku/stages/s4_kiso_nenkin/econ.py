# -*- coding: utf-8 -*-
"""④の経済前提 — 改定率・マクロ経済スライドの調整率・累積調整率・保険料の価格
=============================================================================
③が出した年齢別の改定率（`KOKUKAITE`）と①の単年度の調整率（`waku-m`）から、
スライドを効かせる前後の改定率 `pre_cut` と特別調整率（持ち越し）`T`、そして
「調整を c 年度で終えたとき」の累積調整率 `cut_ruiseki[c, y, x]` を作る。

    名目賃金上昇率[y] = 実質賃金[y] × 物価[y]、運用利回り[y] = 実質利回り[y] × 物価[y]
    pre_cut[y, x] = max(1, min(調整率上限[y] / T[y−1, x−1], 改定率[y, x]))   （持ち越しあり）
                  = max(1, min(調整率上限[y], 改定率[y, x]))                   （持ち越しなし）
    T[y, x]       = T[y−1, x−1] / 調整率上限[y] × pre_cut[y, x]
    cut_ruiseki[c, y, x] = Π_{k ≤ min(c, y)} 1 / pre_cut[k, ξ(k, y, x)]
        ξ = 67 （x ≤ y+67−k のとき）、x − (y+67−k) + 67 （それより上。歳の差だけずらす）

2022〜2024年度は実績（`policy.kiso.macro.actuals`）。名目下限撤廃（`d_macro`）は
2025年度以降の pre_cut を上限そのものにする。保険料の「価格」`kakaku` は
実質賃金の3年平均 × 2年前の物価で、2025年度までは小数3桁に丸める（法定の丸め）。

港: kiso_nenkin/econ.py:econ
仕様: §5.7、§8.4
"""
from dataclasses import dataclass

import numpy as np

from ...axis import YEARS, AGES
from ...econ import c_round_n
from .inputs import AGE_LO, AGE_HI, NA

__all__ = ["KisoEcon", "kiso_econ", "read_max_cut"]


@dataclass
class KisoEcon:
    cpi_up: np.ndarray          # (YEARS.n,) 1 + 物価上昇率
    base_up: np.ndarray         # 名目賃金上昇率
    interest_rate: np.ndarray   # 名目運用利回り
    kakaku: np.ndarray          # 保険料の価格（2004年度 = 1）
    max_cut: np.ndarray         # 単年度の調整率の上限（1 + 調整率）
    kaiteiritu: np.ndarray      # (YEARS.n, AGES.n) 改定率（③の単年度改定率）
    pre_cut: np.ndarray         # (YEARS.n, AGES.n) スライド後／前の比（67〜115歳）
    T: np.ndarray               # (YEARS.n, AGES.n) 特別調整率（持ち越し）
    cut_ruiseki: np.ndarray     # (YEARS.n, YEARS.n, NA) [終了年度 c, 年度 y, 年齢 x−63]


def read_max_cut(path, first_year=2001):
    """①の `waku-m.csv`（西暦, 調整率）→ 1 + 調整率。無い年度は 1、最後の年度より先は最後の値。"""
    from ...io_port import read_year_rows
    rows = read_year_rows(path, 0)
    out = np.ones(YEARS.n)
    last = None
    for y in sorted(rows):
        if YEARS.contains(y) and y >= first_year:
            out[YEARS.i(y)] = 1. + rows[y][0]
            last = y
    if last is not None:
        out[YEARS.i(last) + 1:] = out[YEARS.i(last)]
    return out


def _kakaku(pol, wage_real, cpi_up):
    """保険料の改定に使う価格。港: kiso_nenkin/econ.py:econ（`kakaku_make`）"""
    marume = pol.get("kiso.years.marume_nendo")
    kakaku_nendo = pol.get("kiso.years.kakaku_nendo")
    fixed = {int(k): v for k, v in pol.get("kiso.macro.base_up_avg_fixed").items()}
    avg = np.zeros(YEARS.n)
    base_up_k = np.zeros(YEARS.n)
    kakaku = np.ones(YEARS.n)
    for y in range(YEARS.first + 5, YEARS.last + 1):
        i = YEARS.i(y)
        a = (wage_real[i - 5] * wage_real[i - 4] * wage_real[i - 3]) ** (1. / 3.)
        if y <= marume:
            a = c_round_n(a, 3)
        if y in fixed:
            a = fixed[y]
        avg[i] = a
    for y in range(YEARS.first + 5, YEARS.last + 1):
        i = YEARS.i(y)
        if y in (kakaku_nendo + 2, kakaku_nendo + 3):        # 2006・2007 は物価だけ
            base_up_k[i] = cpi_up[i - 2]
        else:
            base_up_k[i] = avg[i] * cpi_up[i - 2]
            if y <= marume:
                base_up_k[i] = c_round_n(base_up_k[i], 3)
    for y in range(kakaku_nendo + 2, YEARS.last + 1):
        i = YEARS.i(y)
        kakaku[i] = kakaku[i - 1] * base_up_k[i]
        if y <= marume:
            kakaku[i] = c_round_n(kakaku[i], 3)
    return kakaku


def kiso_econ(pol, econ, kaiteiritu, max_cut, carry=0, d_macro=0):
    """`econ`: `kosoku.econ.EconAssumptions`、`kaiteiritu[YEARS.n, AGES.n]`（③の単年度改定率）、
    `max_cut[YEARS.n]`。`carry` 1 で持ち越しあり、`d_macro` 1 で名目下限撤廃。"""
    cpi = econ.cpi_up
    base_up = econ.wage_real_up * cpi
    interest = econ.interest_real_up * cpi
    kakaku = _kakaku(pol, econ.wage_real_up, cpi)

    c_nendo = pol.get("kiso.years.c_nendo")
    kaishi = pol.get("kiso.years.kaishi1")
    actuals = {int(k): v for k, v in pol.get("kiso.macro.actuals").items()}
    xs = AGES.s(67, AGE_HI)
    x0 = AGES.i(67)
    pre = np.ones((YEARS.n, AGES.n))
    T = np.ones((YEARS.n, AGES.n))
    for y in range(kaishi, YEARS.last + 1):
        i = YEARS.i(y)
        if y in actuals:
            a = actuals[y]
            pre[i, xs] = a["pre_cut"] if "pre_cut" in a else 1. / a["pre_cut_div"]
            T[i, xs] = a["T"] if "T" in a else 1. / a["T_div"]
            continue
        if carry:
            # 67歳は前年度の67歳、68歳以上は前年度の1歳下の持ち越しを使う
            t_prev = np.empty(NA - 4)
            t_prev[0] = T[i - 1, x0]
            t_prev[1:] = T[i - 1, x0:AGES.i(AGE_HI)]
            pre[i, xs] = np.maximum(1., np.minimum(max_cut[i] / t_prev, kaiteiritu[i, xs]))
            T[i, xs] = t_prev / max_cut[i] * pre[i, xs]
        else:
            pre[i, xs] = np.maximum(1., np.minimum(max_cut[i], kaiteiritu[i, xs]))
    if d_macro:
        d_m = pol.get("kiso.years.d_m_nendo")
        for y in range(d_m, YEARS.last + 1):
            i = YEARS.i(y)
            if y == d_m:
                t_prev = np.empty(NA - 4)
                t_prev[0] = T[i - 1, x0]
                t_prev[1:] = T[i - 1, x0:AGES.i(AGE_HI)]
                pre[i, xs] = np.maximum(1., max_cut[i] / t_prev)
            else:
                pre[i, xs] = np.maximum(1., max_cut[i])

    # 累積の調整率。k 年度の調整を、k 以降の全部の (c, y, x) に掛け込む
    cr = np.ones((YEARS.n, YEARS.n, NA))
    ages = np.arange(AGE_LO, AGE_HI + 1)
    running = np.ones((YEARS.n, NA))
    for k in range(c_nendo + 1, YEARS.last + 1):
        ki = YEARS.i(k)
        ys = np.arange(k, YEARS.last + 1)
        kyoukai = np.minimum(ys + 67 - k, AGE_HI)[:, None]              # k 年度に67歳だった人の年齢
        age_idx = np.where(ages[None, :] <= kyoukai, 67, ages[None, :] - kyoukai + 67)
        running[ki:] = running[ki:] / pre[ki, AGES.i(age_idx)]
        cr[ki] = running
    return KisoEcon(cpi, base_up, interest, kakaku, max_cut, kaiteiritu, pre, T, cr)
