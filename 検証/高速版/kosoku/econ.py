# -*- coding: utf-8 -*-
"""年金額の改定率と満額 — 経済前提から年度 × 年齢の改定率を作る
==================================================================
③国民年金の `econ.c` の数理をそのまま書いたもの（④基礎年金の `econ.c` も
同じ骨格。④の固有分はフェーズ B で足す）。

    名目賃金指数[y]  = 物価[y−1] × 可処分所得割合の変化[y] × 実質賃金の3年平均[y]
    物価指数[y]      = 物価[y−1]
    単年度改定率[y, x] = 67歳以下: 名目賃金指数 ／ 68歳以上: min(名目賃金, 物価)  （2021年度以降）
    累積改定率[y, x] = 累積[y−1, x−1] × 単年度[y, x]（2024年度までは小数3桁に丸める）
    既裁定の下支え: 累積[y, x] ≥ 0.8 × 累積[y, 67]
    満額[y, x]       = 780,900 × 累積[y, x]（2024年度までは100円単位。以降は丸めた方が
                       大きければ丸める、の旗を前年から引き継ぐ）

法定の丸め（100円単位・小数3桁）は「ロジック」なので残す。丸めの**順序**は
約束しない（`計画.md`「受け入れ基準」）。実績の調整（2015・2019・2020年度の
マクロ経済スライド）は `policy.kokunen.econ.macro_jisseki` から読む。
原本が丸め関数の戻り値を捨てている箇所（台帳 E1）は**そのまま**（E群は据え置き）。

港: nat/econ.py:econ, econ_read, index_make, kaiteiritu_make,
    kaiteiritu_make_before, kaiteiritu_marume, marume_hantei, pension_marume, c_round_n
仕様: §5.7（改定率とマクロ経済スライド）、§5.1（満額）
"""
from dataclasses import dataclass
import math

import numpy as np

from .axis import YEARS, AGES, FIRST_YEAR
from .io_port import lines_of

__all__ = ["EconAssumptions", "read_econ_csv", "KaiteiResult", "kaiteiritu",
           "c_round_n", "pension_marume"]

EPSILON = 1e-14          # 丸め旗の判定（港: nat/setconst.py:213）


def c_round_n(a, n):
    """printf の丸め（最近接・端数は偶数へ）で小数 n 桁に。港: nat/econ.py:c_round_n"""
    return float("%.*f" % (n, a))


def pension_marume(a):
    """100円単位（ちょうど50円は上へ）。港: nat/econ.py:pension_marume"""
    return math.floor((a + 50.) / 100.) * 100


@dataclass(frozen=True)
class EconAssumptions:
    """経済前提。年度の軸（YEARS）で持つ。読めなかった年度は最後の値で延ばす。

    `cpi_up[y]`: 物価上昇率（1 + %/100）、`wage_real_up[y]`: 実質賃金上昇率、
    `interest[y]`: 名目運用利回り（④⑤用。③は使わない）
    """
    cpi_up: np.ndarray
    wage_real_up: np.ndarray
    interest_real_up: np.ndarray
    first_read: int
    last_read: int
    interest_cpi_up: np.ndarray = None      # 対物価の実質運用利回り（列 1。⑤が名目に直して使う）


def read_econ_csv(path):
    """`econ-XXXX.csv`（年度−2000, 名目賃金, 名目利回り, 実質利回り, ×2, 実質賃金, 物価）。

    港: nat/econ.py:econ_read（列 5 = 実質賃金、列 6 = 物価）、
        kiso_nenkin/econ.py（列 2 = 実質運用利回り）
    """
    cpi = YEARS.zeros()
    wage = YEARS.zeros()
    intr = YEARS.zeros()
    icpi = YEARS.zeros()
    first = last = None
    for l in lines_of(path):
        f = [x.strip() for x in l.split(",")]
        if len(f) < 7 or not f[0].lstrip("-").isdigit():
            continue
        y = int(f[0]) + FIRST_YEAR
        if not YEARS.contains(y):
            continue
        i = YEARS.i(y)
        cpi[i] = 1. + float(f[6]) / 100.
        wage[i] = 1. + float(f[5]) / 100.
        intr[i] = 1. + float(f[2]) / 100.
        icpi[i] = 1. + float(f[1]) / 100.
        first = y if first is None else min(first, y)
        last = y if last is None else max(last, y)
    if last is None:
        raise ValueError("%s: 1行も読めない" % path)
    # 最後の年度の値で延ばす
    j = YEARS.i(last)
    cpi[j + 1:] = cpi[j]
    wage[j + 1:] = wage[j]
    intr[j + 1:] = intr[j]
    icpi[j + 1:] = icpi[j]
    return EconAssumptions(cpi, wage, intr, first, last, icpi)


@dataclass(frozen=True)
class KaiteiResult:
    tannen: np.ndarray        # 単年度改定率 [YEARS, AGES]（0〜115歳。116〜120 は 115 と同じ）
    ruiseki: np.ndarray       # 累積改定率  [YEARS, AGES]（2004年度 = 1）
    mangaku: np.ndarray       # 満額        [YEARS, AGES]（円）
    kakyu_12shi: np.ndarray   # 加給単価（第1・2子）[YEARS, AGES]
    kakyu_3shiiko: np.ndarray
    wage_index: np.ndarray    # 名目賃金指数 [YEARS]
    cpi_index: np.ndarray     # 物価指数     [YEARS]


def _indices(pol, econ):
    """名目賃金指数と物価指数。港: nat/econ.py:index_make"""
    marume = pol.get("kokunen.econ.marume_nendo")
    h_start, h_end = pol.get("kokunen.econ.hikiage")
    hokenryo = pol.get("kokunen.econ.hokenryo")
    kasho = pol.get("kokunen.econ.kashobun_start")
    econ_shonendo = pol.get("kokunen.years.econ_shonendo")

    wage_idx = YEARS.zeros()
    cpi_idx = YEARS.zeros()
    for y in range(econ_shonendo + 4, YEARS.last + 1):
        if y in (2005, 2006):
            avg, henka = 1., 1.
        else:
            avg = (econ.wage_real_up[YEARS.i(y - 4)] * econ.wage_real_up[YEARS.i(y - 3)]
                   * econ.wage_real_up[YEARS.i(y - 2)]) ** (1. / 3.)
            if y < h_end + 4:
                henka = ((kasho - hokenryo[y - 3 - h_start] / 2.)
                         / (kasho - hokenryo[y - 4 - h_start] / 2.))
            else:
                henka = 1.
        if y <= marume:
            avg, henka = c_round_n(avg, 3), c_round_n(henka, 3)
        wi = econ.cpi_up[YEARS.i(y - 1)] * henka * avg
        ci = econ.cpi_up[YEARS.i(y - 1)]
        if y <= marume:
            wi, ci = c_round_n(wi, 3), c_round_n(ci, 3)
        wage_idx[YEARS.i(y)] = wi
        cpi_idx[YEARS.i(y)] = ci
    return wage_idx, cpi_idx


def kaiteiritu(pol, econ, tinsura=True, max_age=115):
    """年度 × 年齢の単年度改定率・累積改定率・満額・加給単価。

    港: nat/econ.py:econ
    仕様: §5.7
    """
    cal_start = pol.get("kokunen.econ.cal_start")
    marume = pol.get("kokunen.econ.marume_nendo")
    under67 = pol.get("kokunen.ages.under_67")
    tinsura_kaishi = pol.get("kokunen.years.tinsura_kaishi")
    shitasasae = pol.get("kokunen.kisai_shitasasae")
    macro = {int(k): float(v) for k, v in pol.get("kokunen.econ.macro_jisseki").items()}
    mangaku0 = float(pol.get("kokunen.amounts_2004.mangaku"))
    k12_0 = float(pol.get("kokunen.amounts_2004.kakyu_12shi"))
    k3_0 = float(pol.get("kokunen.amounts_2004.kakyu_3shiiko"))
    shonendo = pol.get("meta.first_year")

    wage_idx, cpi_idx = _indices(pol, econ)
    nx = max_age + 1
    ages = np.arange(nx)
    kt = np.zeros((YEARS.n, nx))
    ru = np.zeros((YEARS.n, nx))
    i0 = YEARS.i(cal_start)
    kt[i0] = 1.
    ru[i0] = 1.

    for y in range(cal_start + 1, YEARS.last + 1):
        i = YEARS.i(y)
        w, c = wage_idx[i], cpi_idx[i]
        if tinsura and y >= tinsura_kaishi:
            # 2021年度以降: 67歳以下は賃金、68歳以上は min(賃金, 物価)
            row = np.where(ages <= under67, w, min(w, c))
        else:
            # 2021年度より前: 「ちょうど67歳」だけ新規裁定の扱い
            if w < 1. and w < c:
                new = 1. if c > 1. else c
            else:
                new = w
            if c > w and w >= 1.:
                old = w
            elif c > 1. and w < 1.:
                old = 1.
            else:
                old = c
            row = np.where(ages == under67, new, old)
        if y in macro:
            row = row * macro[y]          # 実績のマクロ経済スライド（E1: 丸めない）
        kt[i] = row
        prev = ru[i - 1][np.maximum(ages - 1, 0)]
        r = prev * kt[i]
        if y <= marume:
            r = np.array([c_round_n(v, 3) for v in r])
        # 既裁定の下支え（新規裁定の 8割）
        floor = shitasasae * r[under67]
        low = r < floor
        r = np.where(low, floor, r)
        kt[i] = np.where(low, r / prev, kt[i])
        ru[i] = r

    # 100円丸めの旗: 2024年度までは必ず丸め、以降は「前年も丸め済み かつ 累積が動いて
    # いない」ときだけ引き継ぐ
    flg = np.zeros((YEARS.n, nx), dtype=bool)
    for y in range(shonendo, marume + 1):
        flg[YEARS.i(y)] = True
    for y in range(marume + 1, YEARS.last + 1):
        i = YEARS.i(y)
        prev_flg = flg[i - 1][np.maximum(ages - 1, 0)]
        prev_ru = ru[i - 1][np.maximum(ages - 1, 0)]
        flg[i] = prev_flg & (np.abs(ru[i] - prev_ru) < EPSILON)

    mangaku = np.zeros((YEARS.n, nx))
    k12 = np.zeros((YEARS.n, nx))
    k3 = np.zeros((YEARS.n, nx))
    for y in range(shonendo, YEARS.last + 1):
        i = YEARS.i(y)
        base = mangaku0 * ru[i]
        t12 = k12_0 * ru[i, under67]
        t3 = k3_0 * ru[i, under67]
        if y <= marume:
            mangaku[i] = [pension_marume(v) for v in base]
            k12[i] = pension_marume(t12)
            k3[i] = pension_marume(t3)
        else:
            mangaku[i] = np.where(flg[i], np.maximum(base, [pension_marume(v) for v in base]), base)
            f67 = flg[i, under67]
            k12[i] = max(t12, pension_marume(t12)) if f67 else t12
            k3[i] = max(t3, pension_marume(t3)) if f67 else t3

    def widen(a):
        out = np.zeros((YEARS.n, AGES.n))
        out[:, :nx] = a
        out[:, nx:] = a[:, -1:]
        return out
    return KaiteiResult(widen(kt), widen(ru), widen(mangaku), widen(k12), widen(k3),
                        wage_idx, cpi_idx)
