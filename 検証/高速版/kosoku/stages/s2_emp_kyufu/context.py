# -*- coding: utf-8 -*-
"""②の 1 系統・1 種別ぶんの前提をまとめた入れ物
================================================
年度ステップ（`siml.py`）と集計（`shke.py`）が読む定数・基礎率・改定率・外枠を
1 つにまとめる。移植版のグローバル `G` のうち「年度をまたいで変わらないもの」。

港: emp_kyufu/glva.py:zero_init
仕様: §4.3
"""
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ...axis import YEARS, ALL_COHORTS

__all__ = ["Ctx", "cohort_index"]


def cohort_index(year_idx, age):
    """(年度の添字, 年齢) → `ALL_COHORTS` の添字（配列可）。"""
    return YEARS.label(np.asarray(year_idx)) - np.asarray(age) - ALL_COHORTS.first


@dataclass
class Ctx:
    pol: Any
    system: str               # "kou" | "kok" | "ren" | "sig"
    pseid: int
    konen: int
    s: int                    # 種別 1 男 / 2 女 / 3 男女計（厚年の3号）
    xend: int
    tend: int
    sd: Any                   # Seid
    ku: Any                   # Kuriage
    K: Any                    # KisoRates
    E: Any                    # KyufuEcon
    hs: Any                   # Hoshu
    sk: Any                   # ShikyuKaishi（種別 s の表）
    sk_male: Any              # dsitk 用（男・共済）
    sk_female: Any
    sk_total: Any
    rs: np.ndarray            # (4, YEARS.n, NX, 5) 有遺族率
    pop: np.ndarray           # (YEARS.n, 3, NX)
    lpt1: np.ndarray          # (YEARS.n, 4, NX)
    sik: np.ndarray
    nos: np.ndarray
    routsu: np.ndarray
    KIJ: int = 0
    partyr3: int = 0
    flg_part: int = 0
    flg_hiho70: int = 0
    flg_sigo: int = 0
    flg_hantei: int = 0
    lpt2: np.ndarray = None   # 適用拡大（レバー）の増分: 週 30 時間以上
    lpt3: np.ndarray = None   # 同 20〜30 時間
    lpt4: np.ndarray = None   # 同 20 時間未満（kakudai=4 だけ）
    partyr4: int = -1         # 適用拡大（レバー）の年度（YEARS の添字）。flg_part ≥ 1 のときだけ意味を持つ
    kflcan: np.ndarray = None   # 基礎45年化（レバー sigo）の加入可能年数 [年度, 生年度]（ALL_COHORTS）
    flg_kozax: int = 0        # 高在老（65 歳以上）の撤廃（レバー）
    kozaxyr: int = 0          # その年度（YEARS の添字）
    kozax: int = 65           # その年齢
    houjou: int = 0           # 標準報酬上限の見直し 0〜3（レバー）
    houjouyr: int = 0         # 施行年度（YEARS の添字。半年分）
    houjou_r: tuple = (1., 1.)   # 倍率 [男・第3種, 女]
    hihonen: int = 70
    kyuho_last: int = 1925
    C: dict = field(default_factory=dict)      # yaml `kounen.siml` の定数

    @property
    def kou2(self):
        return self.pseid == 0 and self.s <= 2
