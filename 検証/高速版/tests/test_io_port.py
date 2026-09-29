# -*- coding: utf-8 -*-
"""移植版の CSV の読み手: ラベル列で置く（位置で切らない）。
`work/suuri/rev2024` が無ければ飛ばす（`run_pipeline.sh` を1回通すこと）。"""
import os
import sys

import numpy as np
import pytest

from conftest import FAST
sys.path.insert(0, os.path.normpath(os.path.join(FAST, "..")))
import suuri_env                                            # noqa: E402

from kosoku.axis import YEARS, AGES                          # noqa: E402
from kosoku import io_port as IO                             # noqa: E402

CASE = "3001"


def _need(path):
    if not os.path.exists(path):
        pytest.skip("無い: %s（検証/実行/run_pipeline.sh を1回通すこと）" % path)
    return path


def test_kokukaiteは年度と年齢で置く():
    p = _need(suuri_env.suuri("nat", "data", "KOKUKAITE-%s-%sE.csv" % (CASE, CASE)))
    rows = IO.read_year_rows(p, 2000)
    assert min(rows) == 2005 and max(rows) == 2125
    t = IO.read_year_age_table(p, 2000, first_age=0)
    assert t.shape == (YEARS.n, AGES.n)
    # 2006年度の改定率は 0.997（実績）。位置ではなくラベルで置けている
    assert t[YEARS.i(2006), AGES.i(0)] == pytest.approx(0.997)
    assert t[YEARS.i(2004)].sum() == 0.            # 表に無い年度は 0


def test_kaiteaも同じ形():
    p = _need(suuri_env.suuri("emp", "rslt", "u-rev", "kaite", "kaitea-%s-%se" % (CASE, CASE)))
    t = IO.read_year_age_table(p, 2000)
    assert t[YEARS.i(2006), AGES.i(0)] == pytest.approx(0.997)


def test_waku_mとwaku_class():
    d = suuri_env.suuri("wakuc", "rslt", "ver_4_1", "rslt" + CASE)
    m = IO.read_waku_m(_need(os.path.join(d, "waku%s-m.csv" % CASE)))
    assert m.shape == (YEARS.n,)
    assert m[YEARS.i(2005)] == pytest.approx(0.004)
    tables, totals = IO.read_waku_class(_need(os.path.join(d, "waku%s-00.csv" % CASE)))
    key = (0, 0)
    assert key in tables
    assert totals[key][YEARS.i(2021)] == pytest.approx(67382109.)
    # 見出しの年齢ラベルで置いている: 15歳の列が AGES.i(15) に来る
    assert tables[key][YEARS.i(2021), AGES.i(15)] == pytest.approx(28.)
    assert tables[key][YEARS.i(2021), AGES.i(14)] == 0.
    # 計 ≒ 年齢の和（原本の計の列と年齢別の和。丸めのぶんだけ許す）
    np.testing.assert_allclose(tables[key][YEARS.i(2021)].sum(),
                               totals[key][YEARS.i(2021)], rtol=1e-6)
