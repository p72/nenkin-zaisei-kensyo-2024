# -*- coding: utf-8 -*-
"""⑤の経済前提（移植版 `econ.c` 相当）
========================================
    Ri[y]  = (1 + 実質利回り)(1 + 物価) − 1      名目運用利回り
    H[y]   = (1 + 実質賃金)(1 + 物価) − 1        名目賃金上昇率
    2001〜2022年度は実績（`policy.shushi.econ.jisseki`）で Ri と H を上書き
    Ri2[y] = √(1 + Ri[y]) − 1                    半年分（年度途中の収支に掛ける）
    HCdum[y] = (1 + H)/(1 + Ci)                  実質賃金（**上書き前**の H。港の癖）
    Id_Hhd[y] = Id_Hhd[y−1] × (1 + 改定率[y])     保険料改定率の累積（現在価格への換算）
        改定率[y] = (1 + Ci[y−2]) × (1 + 実質賃金の3年幾何平均[y−1]) − 1
        2025年度までは小数3桁に丸めながら積む。2018年度は −0.009 で置き換え。
        2007年度までは物価だけ。価格基準年度（2024）で 1 に正規化
    Id_Cid[y]   = Id_Cid[y−1] × (1 + Ci[y−1])    物価の累積（前年度。物価割り戻し用）
    Id_Cid_2[y] = Id_Cid_2[y−1] × (1 + Ci[y])    同（当年度。事務費の延ばし用）

港: emp_shushi/econ.py:econ, jh_kaite
仕様: §3.2（実質 → 名目）、§3.3（実績年度の上書き）
"""
from dataclasses import dataclass

import numpy as np

from ...axis import YEARS
from ...econ import c_round_n

__all__ = ["ShushiEcon", "shushi_econ"]


@dataclass
class ShushiEcon:
    ri: np.ndarray
    h: np.ndarray
    ci: np.ndarray
    ri2: np.ndarray
    hcdum: np.ndarray
    id_hhd: np.ndarray
    id_cid: np.ndarray
    id_cid_2: np.ndarray


def _nround(x, n):
    """港 `nround`（0 から遠い方へ）。⑤の改定率の丸めはこちら。"""
    d = 10.0 ** n
    v = x * d
    r = np.floor(np.abs(v) + 0.5) * np.sign(v)
    return r / d


def shushi_econ(pol, econ):
    """`econ`: `kosoku.econ.EconAssumptions`（`interest_cpi_up` = 対物価の実質利回り）。"""
    E = pol.get("shushi.econ")
    n = YEARS.n
    read = econ.cpi_up != 0.                          # 読めた年度（2000年度は無い → 0 のまま）
    ci = np.where(read, econ.cpi_up - 1., 0.)
    ri = np.where(read, econ.interest_cpi_up * econ.cpi_up - 1., 0.)
    h = np.where(read, econ.wage_real_up * econ.cpi_up - 1., 0.)
    hcdum = np.where(read, (1. + h) / (1. + ci), 0.)   # 上書き前の H で作る（港の癖）
    for y, v in E["jisseki"].items():
        i = YEARS.i(int(y))
        ri[i] = v[0] / 100.
        h[i] = v[1] / 100.
    ri2 = np.where(read, np.sqrt(1. + ri) - 1., 0.)

    kakaku = YEARS.i(E["kakaku"])
    marume_until = YEARS.i(E["marume_until"])
    ci_until = YEARS.i(E["kaite_ci_until"])
    override = {YEARS.i(int(y)): v for y, v in E["kaite_hp_override"].items()}
    id_hhd = np.ones(n)
    id_cid = np.ones(n)
    id_cid_2 = np.ones(n)
    for i in range(YEARS.i(E["id_hhd_start"]), n):
        jh = (hcdum[i - 3] * hcdum[i - 4] * hcdum[i - 5]) ** (1. / 3.) - 1.   # jh_kaite(k−1)
        if i <= marume_until:
            kaite_ci = _nround(ci[i - 2], 3)
            kaite_hp = _nround((1. + kaite_ci) * _nround(1. + jh, 3), 3) - 1.
            if i <= ci_until:
                kaite_hp = kaite_ci
            if i in override:
                kaite_hp = override[i]
            id_hhd[i] = _nround(id_hhd[i - 1] * (1. + kaite_hp), 3)
        else:
            kaite_hp = (1. + ci[i - 2]) * (1. + jh) - 1.
            id_hhd[i] = id_hhd[i - 1] * (1. + kaite_hp)
        if i > kakaku:
            id_cid[i] = id_cid[i - 1] * (1. + ci[i - 1])
            id_cid_2[i] = id_cid_2[i - 1] * (1. + ci[i])
    id_hhd /= id_hhd[kakaku]
    return ShushiEcon(ri, h, ci, ri2, hcdum, id_hhd, id_cid, id_cid_2)
