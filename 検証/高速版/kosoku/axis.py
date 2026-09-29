# -*- coding: utf-8 -*-
"""年度・年齢・生年度の軸 — 原点はこのファイルにしか書かない
============================================================
移植版は年度と年齢の原点が4通りある（①西暦／②西暦−2000（負あり）＋
`C19`／③西暦のオフセット `nendo - SHONENDO`／④人数と経済で2原点・年齢も
2原点／⑤西暦−2000）。高速版は次の1本に統一する。

    年度   index = 西暦 − 2000            2000〜2125年度（126）
    年齢   index = 年齢                    0〜120歳（121）
    生年度 index = 生年度 − 1926           1926〜2125年度

添字は必ず `YEARS.i(2024)` のような名前付きアクセスで作る。パッケージ内で
`- 2000` のような生の原点を書くことは `tests/test_no_raw_origin.py` が
禁じる。

`Axis` は「ラベル ↔ 添字」の対応と、ラベルの範囲による slice を返すだけの
薄い道具。配列そのものは持たない。
"""
from dataclasses import dataclass

import numpy as np

__all__ = ["Axis", "YEARS", "AGES", "COHORTS", "ALL_COHORTS", "FIRST_YEAR", "LAST_YEAR",
           "MAX_AGE", "FIRST_COHORT", "cohort_of", "age_of", "year_of"]

# ---- 原点はここだけ ------------------------------------------------
FIRST_YEAR = 2000       # 年度の軸の先頭。移植版⑤の `k = 西暦 − 2000` と同じ
LAST_YEAR = 2125        # 推計の最終年度（移植版③ SAISHUNENDO、⑤ ECEDY）
MAX_AGE = 120           # 年齢の軸の末尾。原本の配列は 115〜120 でまちまち
FIRST_COHORT = 1926     # 生年度の先頭（移植版③ N_O_NENDO。大正15年度）


@dataclass(frozen=True)
class Axis:
    """ラベル（年度・年齢・生年度）と添字の対応。

    >>> YEARS.i(2024)
    24
    >>> YEARS.label(24)
    2024
    >>> YEARS.s(2024, 2026)          # 2024〜2026年度（両端を含む）
    slice(24, 27, None)
    """
    name: str
    first: int
    last: int

    @property
    def n(self):
        return self.last - self.first + 1

    def i(self, label):
        """ラベル → 添字。範囲外は落とす（黙って巻き込まない）。"""
        if isinstance(label, np.ndarray):
            if ((label < self.first) | (label > self.last)).any():
                raise IndexError("%s: 範囲外 [%d, %d]" % (self.name, self.first, self.last))
            return label - self.first
        if not (self.first <= label <= self.last):
            raise IndexError("%s: %r は範囲外 [%d, %d]"
                             % (self.name, label, self.first, self.last))
        return label - self.first

    def label(self, index):
        """添字 → ラベル。"""
        return index + self.first

    def s(self, first_label, last_label):
        """ラベルの範囲（両端を含む）→ slice。"""
        return slice(self.i(first_label), self.i(last_label) + 1)

    def labels(self):
        """全ラベルの配列（読み手のラベル列と突き合わせる用）。"""
        return np.arange(self.first, self.last + 1)

    def contains(self, label):
        return self.first <= label <= self.last

    def zeros(self, *extra_shape, dtype=np.float64):
        """この軸を先頭の次元に持つ 0 配列。"""
        return np.zeros((self.n,) + tuple(extra_shape), dtype=dtype)


YEARS = Axis("年度", FIRST_YEAR, LAST_YEAR)
AGES = Axis("年齢", 0, MAX_AGE)
COHORTS = Axis("生年度", FIRST_COHORT, LAST_YEAR)
# 年度 − 年齢が取りうる全域（②の生年度別テーブル用。1926 年度より前は 0 か最初の値）
ALL_COHORTS = Axis("生年度（年度−年齢の全域）", FIRST_YEAR - MAX_AGE, LAST_YEAR)


def cohort_of(year, age):
    """年度と年齢から生年度。原本の慣行どおり「年度 − 年齢」。"""
    return year - age


def age_of(year, cohort):
    return year - cohort


def year_of(cohort, age):
    return cohort + age
