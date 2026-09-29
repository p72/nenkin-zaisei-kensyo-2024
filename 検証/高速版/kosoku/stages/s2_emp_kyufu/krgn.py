# -*- coding: utf-8 -*-
"""繰上げ・繰下げの率（`krgn.cpp`）
==================================
`kragsg_2024.csv` の 60〜64歳の繰上げ請求割合と繰下げ月数の分布から

    riss[x1, x2, s, i]   支給開始年齢 x2 の人が x1 歳で繰上げる割合（65 は残り）
    rigd[s, x1, x2, j]   繰上げ減額率（定額部分ぶん）
    rigk[s, x1, x2, j]   同（報酬比例ぶん）
    rigbe[s, x1, x2, j]  同（基礎年金ぶん）

を作る。`j` は 0（2022年3月以前の裁定。1か月 0.5% 減額）と 1（2022年4月以降。0.4%）。
移植版の `riss` は年度の軸を持つが年度に依らないので、高速版は落とす。
`rkrgn` の女の列は移植版でも使われない（F12）ので男の列だけ使う。

港: emp_kyufu/krgn.py:krgn
仕様: §5.4（繰上げ・繰下げ）
"""
from dataclasses import dataclass

import numpy as np

__all__ = ["Kuriage", "kuriage"]


@dataclass
class Kuriage:
    riss: np.ndarray          # (71, 66, 4, 2)  [x1, x2, s, i]
    rigd: np.ndarray          # (4, 71, 71, 2)  [s, x1, x2, j]
    rigk: np.ndarray
    rigbe: np.ndarray


def kuriage(pol, rkrag, rkrgn):
    """`rkrag[x, s]`（繰上げ請求割合）、`rkrgn[x, s, j]`（繰下げ月数の分布）から。"""
    K = pol.get("kounen.kuriage")
    genritu = (float(K["gengaku_old"]), float(K["gengaku_new"]))       # 1か月あたりの減額率
    riss = np.zeros((71, 66, 4, 2))
    for s in (1, 2, 3):
        tmq = rkrag[:, 1 if s != 2 else 2]
        for i in (0, 1):
            for x2 in range(60, 66):
                riss[65, x2, s, i] = 1.
                for x1 in range(60, x2):
                    if i == 0:
                        riss[x1, x2, s, i] = tmq[x1]
                    riss[65, x2, s, i] -= riss[x1, x2, s, i]
    rigd = np.zeros((4, 71, 71, 2)); rigk = np.zeros((4, 71, 71, 2)); rigbe = np.zeros((4, 71, 71, 2))
    tuki = np.zeros((6, 2))
    for j in (0, 1):
        for x in range(60, 65):
            tuki[x - 60, j] = (1. - rkrgn[x, 1, j]) / genritu[j]
    for s in (1, 2, 3):
        for j in (0, 1):
            g = genritu[j]
            rigd[s, 65, 60, j] = 1.
            rigbe[s, 60, 60, j] = 1.
            for x1 in range(60, 66):
                for x2 in range(61, 66):
                    if x2 < 65:
                        if x1 < x2:
                            rigd[s, x1, x2, j] = (65 - x2) / (tuki[x1 - 60, j] / 12.)
                            rigk[s, x1, x2, j] = (1. - rigd[s, x1, x2, j]) * (1. - tuki[x1 - 60, j] * g)
                            rigbe[s, x1, x2, j] = 1. - (tuki[x1 - 60, j] / 12. - (65 - x2)) * 12. * g
                        elif x1 == 65:
                            rigd[s, x1, x2, j] = (65 - x2) / (tuki[5, j] / 12. + (x1 - x2))
                            rigk[s, x1, x2, j] = 1. - tuki[5, j] * g - rigd[s, x1, x2, j]
                        if x1 == x2:
                            rigbe[s, x1, x2, j] = 1. - tuki[5, j] * g
                    else:
                        rigk[s, x1, x2, j] = 1. - tuki[x1 - 60, j] * g
                        rigbe[s, x1, x2, j] = 1. - tuki[x1 - 60, j] * g
    return Kuriage(riss, rigd, rigk, rigbe)
