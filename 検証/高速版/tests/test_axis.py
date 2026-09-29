# -*- coding: utf-8 -*-
"""軸の約束: 原点は `axis.py` だけ、範囲外は落ちる、ラベルと添字が往復する。"""
import numpy as np
import pytest

from kosoku.axis import (YEARS, AGES, COHORTS, FIRST_YEAR, LAST_YEAR, MAX_AGE,
                         FIRST_COHORT, cohort_of, age_of, year_of)


def test_年度の原点と長さ():
    assert YEARS.i(FIRST_YEAR) == 0
    assert YEARS.i(2024) == 24
    assert YEARS.label(24) == 2024
    assert YEARS.n == LAST_YEAR - FIRST_YEAR + 1 == 126
    assert YEARS.s(2024, 2026) == slice(24, 27)
    assert list(YEARS.labels()[:3]) == [2000, 2001, 2002]


def test_年齢と生年度():
    assert AGES.i(0) == 0 and AGES.i(MAX_AGE) == MAX_AGE and AGES.n == 121
    assert COHORTS.i(FIRST_COHORT) == 0
    assert COHORTS.i(1957) == 31
    assert cohort_of(2024, 67) == 1957
    assert age_of(2024, 1957) == 67
    assert year_of(1957, 67) == 2024


@pytest.mark.parametrize("axis, bad", [(YEARS, 1999), (YEARS, 2126), (AGES, -1),
                                       (AGES, 121), (COHORTS, 1925)])
def test_範囲外は黙って巻き込まない(axis, bad):
    with pytest.raises(IndexError):
        axis.i(bad)


def test_配列のラベルも範囲を見る():
    assert list(YEARS.i(np.array([2000, 2125]))) == [0, 125]
    with pytest.raises(IndexError):
        YEARS.i(np.array([2000, 2126]))


def test_zerosは軸を先頭の次元に持つ():
    a = YEARS.zeros(AGES.n)
    assert a.shape == (126, 121) and a.dtype == np.float64
