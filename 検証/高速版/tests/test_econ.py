# -*- coding: utf-8 -*-
"""改定率と満額が移植版③の出力（`KOKUKAITE` と `PENSION_`）と一致すること。
`work/suuri/rev2024` が無ければ飛ばす。"""
import os
import sys

import numpy as np
import pytest

from conftest import FAST
sys.path.insert(0, os.path.normpath(os.path.join(FAST, "..")))
import suuri_env                                            # noqa: E402

from kosoku.axis import YEARS                                # noqa: E402
from kosoku import io_port as IO                             # noqa: E402
from kosoku.econ import read_econ_csv, kaiteiritu            # noqa: E402
from kosoku.policy import load_policy                        # noqa: E402

CASE = "3001"


def _need(path):
    if not os.path.exists(path):
        pytest.skip("無い: %s" % path)
    return path


@pytest.fixture(scope="module")
def result():
    econ = read_econ_csv(_need(suuri_env.suuri("emp", "data", "u-rev", "econ",
                                               "econ-%s.csv" % CASE)))
    return kaiteiritu(load_policy(), econ)


def test_単年度改定率がKOKUKAITEと一致(result):
    p = _need(suuri_env.suuri("nat", "data", "KOKUKAITE-%s-%sE.csv" % (CASE, CASE)))
    # `KOKUKAITE` は 67〜115歳の欄だけ（港: nat/econ.py:rslt_out）
    rows = IO.read_year_rows(p, 2000)
    for y, v in rows.items():
        got = result.tannen[YEARS.i(y), 67:67 + len(v)]
        np.testing.assert_allclose(got, v, rtol=1e-12, err_msg="%d年度" % y)


def _pension_block(path, title):
    L = IO.lines_of(path)
    start = [i for i, l in enumerate(L) if l.strip().startswith(title)][0]
    rows = {}
    for l in L[start + 1:]:
        f = [x.strip() for x in l.split(",")]
        if not f or not f[0].isdigit():
            if rows:
                break
            continue
        rows[int(f[0])] = np.array([float(x) for x in f[1:] if x != ""])
    return rows


def test_満額と加給単価がPENSIONと一致(result):
    p = _need(suuri_env.suuri("nat", "data", "PENSION_%s-%s-%s.csv" % (CASE, CASE, CASE)))
    for title, arr in (("基礎年金単価", result.mangaku),
                       ("加給単価（第１・２子）", result.kakyu_12shi),
                       ("加給単価（第３子以降）", result.kakyu_3shiiko),
                       ("累積改定率", result.ruiseki)):
        rows = _pension_block(p, title)
        assert rows, title
        for y, v in rows.items():
            y = y if y >= YEARS.first else y + 2000
            got = arr[YEARS.i(y), :len(v)]
            np.testing.assert_allclose(got, v, rtol=1e-12, err_msg="%s %d年度" % (title, y))
