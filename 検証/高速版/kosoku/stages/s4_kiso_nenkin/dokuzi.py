# -*- coding: utf-8 -*-
"""独自給付（死亡一時金・寡婦年金・付加年金）、保険料、業務勘定への繰入
========================================================================
③が出した独自給付の年度末値（`DOKUZI`）を年度間値にし、国民年金の保険料収入と
業務勘定への繰入を作る（移植版 `read_file.c` と `dtst.c` の実績の部分）。

    年度間値 = 前年度末 × (2 + 6) / 12 + 当年度末 × (6 − 2) / 12    （支払遅れ2か月）
    寡婦年金だけ前年度末に改定率（67歳）を掛ける
    保険料月額[y] = 2004年度価格の月額 × 価格[y]（2025年度までは 10円単位に丸める）
    保険料年額[y] = 月額[y−1] × 納付対象[y−1] + 月額[y] × 納付対象[y] × 11
        納付対象 = 1号の算定対象者 − 産休免除 − 育休免除
    業務勘定への繰入: 2024年度までは実績・予算、以降は物価で伸ばして1号被保険者数の比で調整

港: kiso_nenkin/read_file.py:read_file
港: kiso_nenkin/dtst.py:dtst
仕様: §7.1、§7.3
"""
from dataclasses import dataclass, field
import math

import numpy as np

from ...axis import YEARS, AGES
from ...io_port import read_year_rows

__all__ = ["Dokuzi", "read_dokuzi_table", "dokuzi_from_table", "dokuzi_from_natout", "build_dokuzi",
           "build_hokenryou", "SHIHARAIOKURE", "hokenryou_round"]

SHIHARAIOKURE = 2

# `DOKUZI` の列（0 が年度）。港: kiso_nenkin/read_file.py:109-119
FUKA_NINZU = 0
FUKA_NEW, FUKA_OLD_ROREI, FUKA_OLD_TURO = 1, 2, 3
KAFU_NEW, KAFU_OLD_NOUFU, KAFU_OLD_MENJO = 4, 5, 6
ICHIJI_NOUFU, ICHIJI_FUKA = 7, 8


@dataclass
class Dokuzi:
    fuka_ninzu: np.ndarray                                   # (YEARS,)
    fuka_nm: np.ndarray                                      # (YEARS, 3) 新法・旧法老齢・旧法通老
    kafu_nm: np.ndarray                                      # (YEARS, 3) 新法・旧法納付・旧法免除
    ichijikin_nm: np.ndarray                                 # (YEARS, 2) 納付分・付加分
    fuka: np.ndarray = None                                  # 年度間値（同じ並び）
    kafu: np.ndarray = None
    ichijikin: np.ndarray = None
    hokenryou_m: np.ndarray = None                           # (YEARS,) 保険料月額（当年度価格）
    hokenryou_y: np.ndarray = None                           # 保険料年額
    fuka_hokenryou_y: np.ndarray = None
    kodomo_noufukin: np.ndarray = None                       # こども子育て特別会計から繰入
    fukushi: np.ndarray = None                               # 業務勘定への繰入
    yuushi: np.ndarray = None                                # 住宅融資債権（円）

    @property
    def fuka_sum(self):
        return self.fuka.sum(axis=1)

    @property
    def kafu_sum(self):
        return self.kafu.sum(axis=1)

    @property
    def ichijikin_sum(self):
        return self.ichijikin.sum(axis=1)


def read_dokuzi_table(path):
    """③の `DOKUZI` → (YEARS.n, 10)。"""
    D = np.zeros((YEARS.n, 10))
    for y, v in read_year_rows(path, 0).items():
        if YEARS.contains(y) and len(v) >= 10:
            D[YEARS.i(y)] = v[:10]
    return D


def dokuzi_from_table(D):
    """(YEARS.n, 10) の表（`DOKUZI` の列）→ `Dokuzi`（年度末値だけ）。"""
    D = np.asarray(D, dtype=np.float64)
    return Dokuzi(D[:, FUKA_NINZU].copy(), D[:, FUKA_NEW:FUKA_OLD_TURO + 1].copy(),
                  D[:, KAFU_NEW:KAFU_OLD_MENJO + 1].copy(), D[:, ICHIJI_NOUFU:ICHIJI_FUKA + 1].copy())


def dokuzi_from_natout(out):
    return dokuzi_from_table(out.dokuzi["table"])


def hokenryou_round(x):
    """10円単位（0.5 は上へ）。港: kiso_nenkin/cnum.py:Round（b = 1）"""
    return math.floor(x / 10. + 0.5) * 10.


def build_dokuzi(pol, D, kaiteiritu, kakaku, cpi_up, santei, first_year=2021):
    """`D` は `Dokuzi`（年度末値だけ入ったもの）。年度間値・保険料・繰入を埋めて返す。"""
    sho = SHIHARAIOKURE
    i0 = YEARS.i(first_year)
    x67 = AGES.i(pol.get("kiso.ages.under_67"))

    # ---- 年度末値 → 年度間値 ----
    D.ichijikin = np.zeros_like(D.ichijikin_nm)
    D.fuka = np.zeros_like(D.fuka_nm)
    D.kafu = np.zeros_like(D.kafu_nm)
    D.ichijikin[i0:] = (D.ichijikin_nm[i0 - 1:-1] * (sho + 6.) / 12.
                        + D.ichijikin_nm[i0:] * (6. - sho) / 12.)
    D.fuka[i0:] = D.fuka_nm[i0 - 1:-1] * (sho + 6.) / 12. + D.fuka_nm[i0:] * (6. - sho) / 12.
    kt = kaiteiritu[i0:, x67][:, None]
    D.kafu[i0:] = D.kafu_nm[i0 - 1:-1] * (sho + kt * 6.) / 12. + D.kafu_nm[i0:] * (6. - sho) / 12.

    # ---- 業務勘定への繰入 ----
    fk = YEARS.zeros()
    for y, v in pol.get("kiso.fukushi").items():
        fk[YEARS.i(int(y))] = v
    f_nendo = pol.get("kiso.years.fukushi_nendo")
    for y in range(f_nendo + 1, YEARS.last + 1):
        fk[YEARS.i(y)] = fk[YEARS.i(y) - 1] * cpi_up[YEARS.i(y)]
    hk = santei.hiho_kokunen
    fk[YEARS.i(f_nendo) + 1:] *= hk[YEARS.i(f_nendo) + 1:] / hk[YEARS.i(f_nendo)]
    D.fukushi = fk
    return D


def build_hokenryou(pol, D, base, kakaku, santei):
    """保険料月額（価格で改定して丸める）・年額・こども納付金・付加保険料の年額。"""
    marume = YEARS.i(pol.get("kiso.years.marume_nendo"))
    unit = pol.get("kiso.rounding.hokenryou_unit")
    m = base.hokenryou_m0 * kakaku
    for i in range(0, marume + 1):
        m[i] = math.floor(m[i] / unit + 0.5) * unit
    D.hokenryou_m = m
    st1 = santei.by_gou[0, :, 0] - santei.sankyu - santei.ikukyu
    fm = base.fuka_hokenryou_m
    y0 = YEARS.i(pol.get("kiso.years.kaishi1"))
    hy, kd, fy = YEARS.zeros(), YEARS.zeros(), YEARS.zeros()
    hy[y0:] = m[y0 - 1:-1] * st1[y0 - 1:-1] + m[y0:] * st1[y0:] * 11.
    kd[y0:] = m[y0 - 1:-1] * santei.ikukyu[y0 - 1:-1] + m[y0:] * santei.ikukyu[y0:] * 11.
    fy[y0:] = fm[y0 - 1:-1] * D.fuka_ninzu[y0 - 1:-1] + fm[y0:] * D.fuka_ninzu[y0:] * 11.
    D.hokenryou_y, D.kodomo_noufukin, D.fuka_hokenryou_y = hy, kd, fy
    return D
