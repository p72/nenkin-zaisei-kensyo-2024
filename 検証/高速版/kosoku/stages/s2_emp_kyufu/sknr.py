# -*- coding: utf-8 -*-
"""支給開始年齢（特別支給の老齢厚生年金の定額部分 `xxr` と報酬比例部分 `xrb`）
==================================================================================
移植版は `if` を重ねて上書きする書き方（`sknr.cpp`）。高速版は yaml の
`kounen.shikyu_kaishi` の生年度スケジュール（`Schedule`）から**生年度ごとの配列**を
1回作り、年度×年齢で引く。

    xxr[cohort]   定額部分の支給開始年齢
    xrb[cohort]   報酬比例部分の支給開始年齢

種別 `s2 = 3`（男女計。厚年の3号）は移植版が別の表（60→65 を 1958〜1966 年度生で
引き上げ、下側は 1953 年度生以前を 55 まで下げる）を持ち、`xrb = xxr`。これは
被保険者の脱退力（`kiso`）で `u[x > xrb] = 0` にするための帯で、法定の年齢ではない
ので、ここではコードに残す（`_TOTAL_STEPS`）。

港: emp_kyufu/sknr.py:sknr
仕様: §5.4（支給開始年齢）
"""
import numpy as np

from ...axis import COHORTS

__all__ = ["ShikyuKaishi", "shikyu_kaishi"]


# s2 = 3（男女計）の定額部分。港 sknr.py:92-111 の並びを (生年度, 歳) の階段に直したもの。
# 下側は生年度 ≤ 1945 → 55、1946〜47 → 56、…、1952〜53 → 59、1954〜57 → 60、
# 上側は 1958〜59 → 61、…、1966 以降 → 65
_TOTAL_STEPS = ((1926, 55), (1946, 56), (1948, 57), (1950, 58), (1952, 59), (1954, 60),
                (1958, 61), (1960, 62), (1962, 63), (1964, 64), (1966, 65))


class ShikyuKaishi:
    """生年度ごとの支給開始年齢。`xxr(cohorts)` / `xrb(cohorts)` は配列を受け取る。

    生年度が軸の外（1926 年度より前）は最初の値、2125 年度より後は最後の値。
    """

    def __init__(self, xxr_by_cohort, xrb_by_cohort):
        self._xxr = np.asarray(xxr_by_cohort, dtype=np.int64)
        self._xrb = np.asarray(xrb_by_cohort, dtype=np.int64)
        if (self._xrb > self._xxr).any() or (self._xxr > 65).any() or (self._xrb < 55).any():
            raise ValueError("支給開始年齢: 報酬比例 ≤ 定額 ≤ 65、報酬比例 ≥ 55 でない")

    def _idx(self, cohorts):
        c = np.asarray(cohorts)
        return np.clip(c - COHORTS.first, 0, COHORTS.n - 1)

    def xxr(self, cohorts):
        return self._xxr[self._idx(cohorts)]

    def xrb(self, cohorts):
        return self._xrb[self._idx(cohorts)]


def _steps_to_array(points):
    out = np.zeros(COHORTS.n, dtype=np.int64)
    c = COHORTS.labels()
    v = points[0][1]
    for key, val in points:
        out[c >= key] = val
    out[c < points[0][0]] = v
    return out


def shikyu_kaishi(pol, s2, konen):
    """種別 `s2`（1 男 / 2 女 / 3 男女計）の支給開始年齢表。共済（`konen = 0`）は男の表。"""
    if s2 == 3 and konen:
        xxr = _steps_to_array(_TOTAL_STEPS)
        return ShikyuKaishi(xxr, xxr)
    sex = "female" if (s2 == 2 and konen) else "male"
    xxr = _steps_to_array(pol.schedule("kounen.shikyu_kaishi.teigaku_" + sex).points)
    xrb = _steps_to_array(pol.schedule("kounen.shikyu_kaishi.hirei_" + sex).points)
    return ShikyuKaishi(xxr, xrb)
