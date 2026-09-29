# -*- coding: utf-8 -*-
"""②の経済前提と改定率（移植版 `econ.cpp` 相当）
===================================================
名目の率（`ri` `h` `ci0`。2001〜2022年度は実績で上書き）から、年金額の改定率を
年度・年齢で組み立てる。本来水準（賃金／物価）と特例水準（従前額保障）の高い方を
使う、という 2004〜2024 年度の制度をそのまま持つ。

    id_hh_juzen[k]        従前額保障の水準（物価スライド）
    id_hh_hon0[k][x]      本来水準（67歳は賃金、68歳以上は物価。生年でずれる）
    id_hh_toku[k][x]      特例水準（`tamari_ci` = 物価下落の「たまり」が解消するまで）
    id_hh_siku[k][x]      適用する水準 = max(本来（67歳の8割を下限）, 特例)
    arv_hh[k][x]          定額系の改定率（前年度からの伸び）→ `kaiteb`
    arv_hp[k][x]          報酬比例の改定率（`idg_hp_*`。7809円・8042円の単価で持つ）→ `kaitea`
    hh / ci               賃金・物価の改定率、ci2 / hp2 は年齢別（従前額・比例）
    jz_shk / dir          従前額保障の水準と可処分所得割合の累積（`simlbzw` の cht）
    ad / ad2 / bd[j]      賃金の累積・比例改定率の累積（2004年度 0.988）・給付種別ごとの累積

`tamari_ci < 0 || k <= 2024` のあいだは小数3桁・4桁に丸めながら積む（法定の丸め）。

港: emp_kyufu/econ.py:econ
仕様: §5.7（改定率）、§3.2〜3.3
"""
from dataclasses import dataclass
import math

import numpy as np

from ...axis import YEARS
from ...econ import EconAssumptions

__all__ = ["KyufuEcon", "kyufu_econ", "roundn", "c_round"]

NXE = 116


def c_round(x):
    """C99 の round()（0 から遠い方へ）。港: emp_kyufu/sepsstd.py:roundn"""
    t = float(math.trunc(x))
    d = x - t
    if d >= 0.5:
        return t + 1.
    if d <= -0.5:
        return t - 1.
    return t


def roundn(v, n):
    """`round(v × 10^n) / 10^n`。港: emp_kyufu/sepsstd.py:roundn"""
    p = 10.0 ** n
    return c_round(v * p) / p


def _roundn_arr(a, n):
    p = 10.0 ** n
    v = a * p
    return (np.floor(np.abs(v) + 0.5) * np.sign(v)) / p


_SAME = (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 14, 14, 14, 6, 4, 5, 5, 13, 4)


@dataclass
class KyufuEcon:
    ri: np.ndarray
    h: np.ndarray
    ci0: np.ndarray
    hdum: np.ndarray
    hh: np.ndarray
    ci: np.ndarray
    ci2: np.ndarray           # (YEARS.n+3, NXE)
    hp2: np.ndarray
    jz_shk: np.ndarray
    dir: np.ndarray
    ad: np.ndarray
    ad2: np.ndarray
    bd: np.ndarray            # (YEARS.n, 24)
    rv: np.ndarray
    arv_hh: np.ndarray        # (YEARS.n+3, NXE) → kaiteb
    arv_hp: np.ndarray        # → kaitea
    hh2: tuple                # 1999〜2001 年度の特例
    jh_kaite: np.ndarray
    koujor: np.ndarray


def kyufu_econ(pol, econ, ke):
    """`econ`: `EconAssumptions`（列 1 対物価の実質利回り、列 5 実質賃金、列 6 物価）。"""
    E = pol.get("kounen.econ")
    n = YEARS.n + 3                                   # 港の ECEDY = 2128 まで
    kijun = YEARS.i(pol.get("kounen.years.kijun"))
    ke = YEARS.i(ke)
    marume_yr = YEARS.i(E["marume_yr"])
    ridum = np.zeros(n); hdum = np.zeros(n); ci0 = np.zeros(n)
    ri = np.zeros(n); h = np.zeros(n)
    read = econ.cpi_up != 0.
    last = int(np.nonzero(read)[0].max())
    for k in range(1, ke + 1):
        kk = min(k, last)
        ridum[k] = econ.interest_cpi_up[kk] - 1.
        hdum[k] = econ.wage_real_up[kk] - 1.
        ci0[k] = econ.cpi_up[kk] - 1.
        ri[k] = (1. + ridum[k]) * (1. + ci0[k]) - 1.
        h[k] = (1. + hdum[k]) * (1. + ci0[k]) - 1.
    for y, v in pol.get("shushi.econ.jisseki").items():        # 実績は⑤と同じ表
        i = YEARS.i(int(y))
        ri[i] = v[0] * 1e-2
        h[i] = v[1] * 1e-2

    jh_kaite = np.zeros(n); koujor = np.zeros(n)
    for k in range(5, ke + 1):
        jh_kaite[k] = ((1. + hdum[k - 4]) * (1. + hdum[k - 3]) * (1. + hdum[k - 2])) ** (1. / 3.)
    P = E["prema"]
    prema = np.zeros(n)
    prema[YEARS.i(P["base_year"])] = P["base"]
    for k in range(YEARS.i(P["base_year"]) + 1, ke + 1):
        prema[k] = min(prema[k - 1] + P["step"], P["cap"])
    kb = E["kashobun"]
    for k in range(5, ke + 1):
        koujor[k] = 1. if k <= 6 else (kb - prema[k - 3] / 2.) / (kb - prema[k - 4] / 2.)

    id_hh_juzen = np.zeros(n); id_hh_hon0 = np.zeros((n, NXE)); id_hh_honju8w = np.zeros((n, NXE))
    id_hh_toku = np.zeros((n, NXE)); id_hh_siku = np.zeros((n, NXE)); arv_hh = np.zeros((n, NXE))
    idr_hp_hon = np.zeros((n, NXE)); idg_hp_hon8w = np.zeros((n, NXE)); idr_hp_toku = np.zeros((n, NXE))
    idg_hp_toku = np.zeros((n, NXE)); idg_hp_siku = np.zeros((n, NXE)); arv_hp = np.zeros((n, NXE))
    hh = np.zeros(n); ci = np.zeros(n); ci2 = np.zeros((n, NXE)); hp2 = np.zeros((n, NXE))
    jz_shk = np.zeros(n); dr = np.zeros(n)
    I = E["init_2004"]
    k4 = YEARS.i(I["year"])
    tamari_ci = E["tamari_init"]
    id_hh_juzen[k4] = I["hh_juzen"]
    for x, v in I["hh_hon0"].items():
        id_hh_hon0[k4, int(x)] = v
    id_hh_hon0[k4, 73] = id_hh_hon0[k4, 72] * I["hon0_73"][0] / I["hon0_73"][1]
    id_hh_hon0[k4, 74] = id_hh_hon0[k4, 72] * I["hon0_74"][0] / I["hon0_74"][1]
    id_hh_hon0[k4, 75] = id_hh_hon0[k4, 72] * I["hon0_75"][0] / I["hon0_75"][1]
    id_hh_honju8w[k4, 67] = max(max(id_hh_juzen[k4], id_hh_hon0[k4, 67]), id_hh_hon0[k4, 67] * 0.8)
    id_hh_toku[k4, 67] = I["hh_toku"]
    id_hh_siku[k4, 67] = max(id_hh_honju8w[k4, 67], id_hh_toku[k4, 67])
    U_HON, U_TOKU = I["hp_hon_unit"], I["hp_toku_unit"]
    idr_hp_hon[k4, 67] = 1.
    idg_hp_hon8w[k4, 67] = U_HON
    idr_hp_toku[k4, 67] = I["hp_toku"]
    idg_hp_toku[k4, 67] = c_round(idr_hp_toku[k4, 67] * U_TOKU)
    idg_hp_siku[k4, 67] = max(idg_hp_hon8w[k4, 67], idg_hp_toku[k4, 67])
    for x in range(68, NXE):
        if x >= 76:
            id_hh_hon0[k4, x] = id_hh_hon0[k4, 75]
        id_hh_honju8w[k4, x] = max(max(id_hh_juzen[k4], id_hh_hon0[k4, x]), id_hh_hon0[k4, 67] * 0.8)
        id_hh_toku[k4, x] = id_hh_toku[k4, 67]
        id_hh_siku[k4, x] = max(id_hh_honju8w[k4, x], id_hh_toku[k4, x])
        idr_hp_hon[k4, x] = idr_hp_hon[k4, 67]
        idg_hp_hon8w[k4, x] = idg_hp_hon8w[k4, 67]
        idr_hp_toku[k4, x] = idr_hp_toku[k4, 67]
        idg_hp_toku[k4, x] = idg_hp_toku[k4, 67]
        idg_hp_siku[k4, x] = idg_hp_siku[k4, 67]
    jz_shk[k4] = roundn(I["jz_shk"][0] / I["jz_shk"][1], 3)
    dr[k4] = I["dir"]
    ci_kijun = 1.
    chinsura = pol.get("kounen.flags.chinsura")
    flg_kaisho = pol.get("kounen.flags.flg_kaisho")
    xs = np.arange(68, NXE)

    for k in range(k4 + 1, ke + 1):
        kaite_ci = ci0[k - 1]
        kaite_hh = (1. + kaite_ci) * jh_kaite[k] * koujor[k] - 1.
        kaite_cird = roundn(ci0[k - 1], 3)
        kaite_hhrd = roundn((1. + kaite_cird) * roundn(jh_kaite[k], 3) * roundn(koujor[k], 3) - 1., 3)
        hhd, cid = kaite_hh, kaite_ci
        if k < kijun:
            if hhd < cid and hhd < 0.:
                kaite_hh = min(cid, 0.)
            if hhd < cid and cid > 0.:
                kaite_ci = max(hhd, 0.)
        elif hhd < cid:
            kaite_ci = hhd
        if tamari_ci >= 0. and k > marume_yr:
            if k >= kijun:
                jz_shk[k] = jz_shk[k - 1] / (1. + ci0[k - 1]) / jh_kaite[k]
            else:
                if hhd < cid and hhd < 0. and cid < 0.:
                    jz_shk[k] = jz_shk[k - 1] / (1. + ci0[k - 1])
                elif hhd < cid and hhd < 0. and cid >= 0.:
                    jz_shk[k] = jz_shk[k - 1]
                else:
                    jz_shk[k] = jz_shk[k - 1] / (1. + ci0[k - 1]) / jh_kaite[k]
        hhd, cid = kaite_hhrd, kaite_cird
        if k < kijun:
            if hhd < cid and hhd < 0.:
                kaite_hhrd = min(cid, 0.)
            if hhd < cid and cid > 0.:
                kaite_cird = max(hhd, 0.)
        elif hhd < cid:
            kaite_cird = hhd
        if tamari_ci < 0. or k <= marume_yr:
            if k >= kijun:
                jz_shk[k] = roundn((jz_shk[k - 1] / (1. + ci0[k - 1])) / roundn(jh_kaite[k], 3), 3)
            else:
                if hhd < cid and hhd < 0. and cid < 0.:
                    jz_shk[k] = roundn(jz_shk[k - 1] / (1. + ci0[k - 1]), 3)
                elif hhd < cid and hhd < 0. and cid >= 0.:
                    jz_shk[k] = jz_shk[k - 1]
                else:
                    jz_shk[k] = roundn((jz_shk[k - 1] / (1. + ci0[k - 1])) / roundn(jh_kaite[k], 3), 3)
        if k >= YEARS.i(E["hp_from_hh_year"]):
            kaite_hp, kaite_hprd = kaite_hh, kaite_hhrd
        else:
            kaite_hp, kaite_hprd = kaite_ci, kaite_cird
        ci_kijun = roundn(ci_kijun * (1. + ci0[k - 1]), 3)
        if ci_kijun < 1.:
            cid = ci_kijun - 1.
            ci_kijun = 1.
        else:
            cid = 0.
        hhd = cid
        if flg_kaisho == 2:
            kaisho = E["tokurei_kaisho"]
            ks_years = [YEARS.i(int(y)) for y in kaisho["years"]]
            if k in ks_years:
                hhd = min(1., roundn((1. + kaite_hhrd) * kaisho["rate"], 3)) - 1.
                cid = min(1., roundn((1. + kaite_cird) * kaisho["rate"], 3)) - 1.
            elif k >= YEARS.i(kaisho["done_from"]):
                hhd = -1.
                cid = -1.
        if tamari_ci < 0. or k <= marume_yr:
            id_hh_juzen[k] = roundn(id_hh_juzen[k - 1] * (1. + kaite_cird), 4)
            id_hh_hon0[k, 67] = roundn(id_hh_hon0[k - 1, 67] * (1. + kaite_hhrd), 4)
            id_hh_hon0[k, xs] = _roundn_arr(id_hh_hon0[k - 1, xs - 1] * (1. + kaite_cird), 4)
            dr[k] = roundn(dr[k - 1] * roundn(koujor[k], 3), 3)
        else:
            id_hh_juzen[k] = id_hh_juzen[k - 1] * (1. + kaite_ci)
            id_hh_hon0[k, 67] = id_hh_hon0[k - 1, 67] * (1. + kaite_hh)
            id_hh_hon0[k, xs] = id_hh_hon0[k - 1, xs - 1] * (1. + kaite_ci)
            dr[k] = dr[k - 1] * koujor[k]
        id_hh_honju8w[k, 67] = max(max(id_hh_juzen[k], id_hh_hon0[k, 67]), id_hh_hon0[k, 67] * 0.8)
        id_hh_toku[k, 67] = roundn(id_hh_toku[k - 1, 67] * (1. + hhd), 4)
        if k == YEARS.i(E["toku_fix"]["year"]):
            id_hh_toku[k, 67] = E["toku_fix"]["value"]
        id_hh_siku[k, 67] = max(id_hh_honju8w[k, 67], id_hh_toku[k, 67])
        if id_hh_honju8w[k, 67] < id_hh_toku[k, 67]:
            arv_hh[k, 67] = 1. + hhd
        elif k <= marume_yr and id_hh_honju8w[k - 1, 67] >= id_hh_toku[k - 1, 67]:
            arv_hh[k, 67] = roundn(id_hh_siku[k, 67] / id_hh_siku[k - 1, 67], 3)
        else:
            arv_hh[k, 67] = id_hh_siku[k, 67] / id_hh_siku[k - 1, 67]
        if idg_hp_hon8w[k - 1, 67] < idg_hp_toku[k - 1, 67] or k <= marume_yr:
            idr_hp_hon[k, 67] = roundn(idr_hp_hon[k - 1, 67] * (1. + kaite_hprd), 3)
            idg_hp_hon8w[k, 67] = c_round(idr_hp_hon[k, 67] * U_HON)
        else:
            idr_hp_hon[k, 67] = idr_hp_hon[k - 1, 67] * (1. + kaite_hp)
            idg_hp_hon8w[k, 67] = idg_hp_hon8w[k - 1, 67] * (1. + kaite_hp)
        idr_hp_toku[k, 67] = roundn(idr_hp_toku[k - 1, 67] * (1. + hhd), 3)
        idg_hp_toku[k, 67] = c_round(idr_hp_toku[k, 67] * U_TOKU)
        idg_hp_siku[k, 67] = max(idg_hp_hon8w[k, 67], idg_hp_toku[k, 67])
        if idg_hp_hon8w[k, 67] < idg_hp_toku[k, 67]:
            arv_hp[k, 67] = 1. + hhd
        elif k <= marume_yr and idg_hp_hon8w[k - 1, 67] >= idg_hp_toku[k - 1, 67]:
            arv_hp[k, 67] = roundn(idg_hp_siku[k, 67] / idg_hp_siku[k - 1, 67], 3)
        else:
            arv_hp[k, 67] = idg_hp_siku[k, 67] / idg_hp_siku[k - 1, 67]
        # ---- 68 歳以上（前年度の 1 歳下から） ----
        id_hh_honju8w[k, xs] = np.maximum(np.maximum(id_hh_juzen[k], id_hh_hon0[k, xs]), id_hh_hon0[k, 67] * 0.8)
        id_hh_toku[k, xs] = _roundn_arr(id_hh_toku[k - 1, xs - 1] * (1. + cid), 4)
        if k == YEARS.i(E["toku_fix"]["year"]):
            id_hh_toku[k, xs] = E["toku_fix"]["value"]
        id_hh_siku[k, xs] = np.maximum(id_hh_honju8w[k, xs], id_hh_toku[k, xs])
        c1 = id_hh_honju8w[k, xs] < id_hh_toku[k, xs]
        c2 = (k <= marume_yr) & (id_hh_honju8w[k - 1, xs - 1] >= id_hh_toku[k - 1, xs - 1])
        ratio = id_hh_siku[k, xs] / id_hh_siku[k - 1, xs - 1]
        arv_hh[k, xs] = np.where(c1, 1. + cid, np.where(c2, _roundn_arr(ratio, 3), ratio))
        c3 = idg_hp_hon8w[k - 1, xs - 1] < idg_hp_toku[k - 1, xs - 1]
        hon_r = _roundn_arr(idr_hp_hon[k - 1, xs - 1] * (1. + kaite_cird), 3)
        hon_g_r = _roundn_arr(np.maximum(hon_r, idr_hp_hon[k, 67] * 0.8) * U_HON, 0)
        hon_n = idr_hp_hon[k - 1, xs - 1] * (1. + kaite_ci)
        hon_g_n = np.maximum(idg_hp_hon8w[k, 67] * 0.8, idg_hp_hon8w[k - 1, xs - 1] * (1. + kaite_ci))
        idr_hp_hon[k, xs] = np.where(c3, hon_r, hon_n)
        idg_hp_hon8w[k, xs] = np.where(c3, hon_g_r, hon_g_n)
        idr_hp_toku[k, xs] = _roundn_arr(idr_hp_toku[k - 1, xs - 1] * (1. + cid), 3)
        idg_hp_toku[k, xs] = _roundn_arr(idr_hp_toku[k, xs] * U_TOKU, 0)
        idg_hp_siku[k, xs] = np.maximum(idg_hp_hon8w[k, xs], idg_hp_toku[k, xs])
        c4 = idg_hp_hon8w[k, xs] < idg_hp_toku[k, xs]
        c5 = (k <= marume_yr) & (idg_hp_hon8w[k - 1, xs - 1] >= idg_hp_toku[k - 1, xs - 1])
        ratio = idg_hp_siku[k, xs] / idg_hp_siku[k - 1, xs - 1]
        arv_hp[k, xs] = np.where(c4, 1. + cid, np.where(c5, _roundn_arr(ratio, 3), ratio))
        if tamari_ci < 0. or k <= marume_yr:
            hh[k], ci[k] = kaite_hhrd, kaite_cird
        else:
            hh[k], ci[k] = kaite_hh, kaite_ci
        if id_hh_juzen[k] < id_hh_toku[k, 67]:
            ci2[k, 67] = hhd
        elif id_hh_juzen[k - 1] < id_hh_toku[k - 1, 67]:
            ci2[k, 67] = id_hh_juzen[k] / id_hh_toku[k - 1, 67] - 1.
        else:
            if chinsura == 1 and k >= kijun:
                ci2[k, 67] = ci[k]
            else:
                ci2[k, 67] = 0. if (hhd < 0. and cid > 0.) else ci[k]
        d1 = id_hh_juzen[k] < id_hh_toku[k, xs]
        d2 = id_hh_juzen[k - 1] < id_hh_toku[k - 1, xs - 1]
        with np.errstate(divide="ignore", invalid="ignore"):      # 特例水準が 0 の年齢は d2 が偽で使わない
            ci2[k, xs] = np.where(d1, cid, np.where(d2, id_hh_juzen[k] / id_hh_toku[k - 1, xs - 1] - 1., ci[k]))
        if idg_hp_hon8w[k - 1, 67] < idg_hp_toku[k - 1, 67]:
            hp2[k, 67] = arv_hp[k, 67] - 1.
        else:
            hp2[k, 67] = kaite_hprd if k <= marume_yr else kaite_hp
        hp2[k, xs] = np.where(c3, arv_hp[k, xs] - 1., kaite_cird if k <= marume_yr else kaite_ci)
        tamari_ci = roundn(tamari_ci + kaite_cird - cid, 3)

    hh2 = tuple(E["hh2"])
    for k in range(1, k4 + 1):
        ci[k] = 0.
        if k in (k4 - 1, k4):
            ci[k] = ci0[k - 1]
        ci2[k, 67:] = ci[k]
        hp2[k, 67:] = ci[k]

    rv = np.zeros((n, 24))
    for j in range(1, 24):
        for k in range(1, ke + 1):
            if j <= 14 and j != 13:
                if k <= k4 - 1:
                    rv[k, j] = ci[k] if k >= k4 - 1 else 0.
                elif k == k4:
                    if j in (1, 10):
                        v = (1. + ci0[k4 - 1]) * roundn((1. + hh2[0]) * (1. + hh2[1]) * (1. + hh2[2]), 3)
                        rv[k, j] = roundn(v, 3) - 1.
                    else:
                        rv[k, j] = hp2[k, 67]
                else:
                    rv[k, j] = hh[k] if j in (1, 10) else hp2[k, 67]
            elif j == 13:
                rv[k, j] = 0.
            else:
                rv[k, j] = rv[k, _SAME[j]]
    ad = np.zeros(n); ad2 = np.zeros(n); bd = np.zeros((n, 24))
    ad[kijun] = 1.
    for k in range(kijun + 1, ke + 1):
        ad[k] = ad[k - 1] * (1. + h[k])
        if k <= marume_yr:
            ad[k] = roundn(ad[k], 3)
    ad2[k4] = E["ad2_init"]
    extra = {YEARS.i(int(y)): v for y, v in E["ad2_extra"].items()}
    for k in range(k4 + 1, kijun + 1):
        ad2[k] = ad2[k - 1] * (1. + hp2[k, 67]) * extra.get(k, 1.)
        if k <= marume_yr:
            ad2[k] = roundn(ad2[k], 3)
    for j in range(1, 24):
        bd[kijun, j] = 1.
        for k in range(kijun + 1, ke + 1):
            bd[k, j] = bd[k - 1, j] * (1. + rv[k, j])
            if k <= marume_yr:
                bd[k, j] = roundn(bd[k, j], 3)
    return KyufuEcon(ri, h, ci0, hdum, hh, ci, ci2, hp2, jz_shk, dr, ad, ad2, bd, rv, arv_hh, arv_hp,
                     hh2, jh_kaite, koujor)
