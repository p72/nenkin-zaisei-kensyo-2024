# -*- coding: utf-8 -*-
"""②の年度ごとの状態（種別 `s` ごとに 1 つ）
============================================
移植版の `glva.py` の配列群のうち、年度をまたいで持ち越すもの・年度内で使い回す
作業配列を 1 つの入れ物にまとめる。年度の軸を持つ配列は `q2`・`l`・`lpt` だけ
（他は当年度の値を上書きしていく）。添字の約束は移植版のまま:

    x 0〜115 年齢、t 0〜100 加入からの経過年、xx 0〜15 繰上げ繰下げの区分
    （0 = 65歳裁定、1〜5 = 繰上げ 64〜60歳、6〜10 = 繰下げ 66〜70歳）、
    i 1〜13 給付の種類、j 1〜23 年金額の内訳

港: emp_kyufu/glva.py:zero_sepsd
仕様: §4.3（記号）
"""
from dataclasses import dataclass, field, fields

import numpy as np

from ...axis import YEARS
from .inputs import NX, NT, NXX, NI, NJ

__all__ = ["State", "new_state"]


def _z(*shape):
    return field(default_factory=lambda: np.zeros(shape))


@dataclass
class State:
    # 被保険者
    g: np.ndarray = _z(NX, NT)          # 被保険者
    ge: np.ndarray = _z(NX, NT)         # 受給待期
    gpt: np.ndarray = _z(NX, NT)        # うちパート
    bb: np.ndarray = _z(NX, NT)         # 平均標準報酬（累積）
    bbpt: np.ndarray = _z(NX, NT)
    bbnp: np.ndarray = _z(NX, NT)
    gz: np.ndarray = _z(NX, NT)
    gzpt: np.ndarray = _z(NX, NT)
    gn: np.ndarray = _z(NX, NT)
    gnpt: np.ndarray = _z(NX, NT)
    gez: np.ndarray = _z(NX, NT)
    ye: np.ndarray = _z(NX, NT)
    gnn: np.ndarray = _z(NX)
    gnnpt: np.ndarray = _z(NX)
    y: np.ndarray = _z(NX, NT, 4)
    ypt: np.ndarray = _z(NX, NT, 4)
    z: np.ndarray = _z(NX, NT, 2, 10)   # 標準報酬の内訳（在職）
    ze: np.ndarray = _z(NX, NT, 2, 10)  # 同（待期）
    w: np.ndarray = _z(NX, NT, 1, 8, 4)
    we: np.ndarray = _z(NX, NT, 1, 8, 4)
    chwd: np.ndarray = _z(NX, NT, 4)
    gd: np.ndarray = _z(NX, NT)         # 在職の待機
    q2: np.ndarray = _z(YEARS.n, NX)    # 実績から逆算した死亡率
    # 受給権者
    r: np.ndarray = _z(NX, NXX, NI)
    rn: np.ndarray = _z(NX, NXX, NI)
    hn: np.ndarray = _z(NX, NXX, NI, 5)
    hnn: np.ndarray = _z(NX, NXX, NI, 5)
    f: np.ndarray = _z(NX, NXX, NI, NJ)
    fn: np.ndarray = _z(NX, NXX, NI, NJ)
    f_hik: np.ndarray = _z(NX, NXX, NI, NJ)
    f_min: np.ndarray = _z(NX, NXX, NI, NJ)
    fnhik: np.ndarray = _z(NX, NXX, NI, NJ)
    fnmin: np.ndarray = _z(NX, NXX, NI, NJ)
    pshn: np.ndarray = _z(NX, NXX, NI)
    pshnn: np.ndarray = _z(NX, NXX, NI)
    # 長期加入者の特例
    rsen: np.ndarray = _z(NX)
    rsenn: np.ndarray = _z(NX)
    hnsen: np.ndarray = _z(NX, 3)
    hnsenn: np.ndarray = _z(NX, 3)
    pshnsen: np.ndarray = _z(NX)
    pshnsenn: np.ndarray = _z(NX)
    fsen: np.ndarray = _z(NX, NJ)
    fsenmin: np.ndarray = _z(NX, NJ)
    fsenhik: np.ndarray = _z(NX, NJ)
    fsenn: np.ndarray = _z(NX, NJ)
    fsennhik: np.ndarray = _z(NX, NJ)
    fsennmin: np.ndarray = _z(NX, NJ)
    fkouzai2: np.ndarray = _z(NX, 11, 3)
    # 判定補正・パート
    rhantei: np.ndarray = _z(NX, NXX, NI)
    fhantei: np.ndarray = _z(NX, NXX, NI, NJ)
    fpart: np.ndarray = _z(NX, NXX, 3)
    fpart2: np.ndarray = _z(NX, NXX, 3)
    # 外枠（simlg が丸め誤差ぶんを動かすので複製を持つ）
    l: np.ndarray = _z(YEARS.n, 4, NX)
    lpt: np.ndarray = _z(YEARS.n, 4, NX)

    def names(self):
        return [f.name for f in fields(self)]


def new_state(l, lpt):
    st = State()
    st.l = np.array(l, dtype=np.float64)
    st.lpt = np.array(lpt, dtype=np.float64)
    return st
