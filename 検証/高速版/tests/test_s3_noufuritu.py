# -*- coding: utf-8 -*-
"""納付率の将来推計が移植版③の出力 `nat_wariai`（第1号の納付区分別の割合）と
一致すること。`work/suuri/rev2024` が無ければ飛ばす。"""
import os
import sys

import numpy as np
import pytest

from conftest import FAST
sys.path.insert(0, os.path.normpath(os.path.join(FAST, "..")))
import suuri_env                                            # noqa: E402

from kosoku.axis import YEARS, AGES                          # noqa: E402
from kosoku.io_port import lines_of                          # noqa: E402
from kosoku.policy import load_policy                        # noqa: E402
from kosoku.stages.s3_nat.inputs import read_sotowaku, MALE, FEMALE   # noqa: E402
from kosoku.stages.s3_nat import noufuritu as NF             # noqa: E402

CASE = "3001"


def _need(path):
    if not os.path.exists(path):
        pytest.skip("無い: %s" % path)
    return path


@pytest.fixture(scope="module")
def result():
    kis = _need(suuri_env.suuri("nat", "base_data", "kisoritu"))
    waku = _need(suuri_env.suuri("wakuc", "rslt", "ver_4_1", "rslt" + CASE))
    inputs = NF.read_noufu_inputs(kis, os.path.join(kis, "birth_ratio_0.csv"))
    sw = read_sotowaku(waku, CASE)
    return NF.noufuritu(load_policy(), inputs, sw)


def test_nat_wariaiと一致(result):
    p = _need(suuri_env.suuri("nat", "data", "nat_wariai%s-%s.csv" % (CASE, CASE)))
    n_rows = 0
    worst = 0.
    for l in lines_of(p)[1:]:
        f = [x.strip() for x in l.split(",")]
        if len(f) < 13 or not f[0].isdigit():
            continue
        sex = MALE if int(f[0]) == 1 else FEMALE
        y, x = int(f[1]), int(f[2])
        v = np.array([float(t) for t in f[3:13]])
        N = result.noufuritu[sex][YEARS.i(y), AGES.i(x)]
        F = result.noufuritu_fuka[sex][YEARS.i(y), AGES.i(x)]
        got = np.array([N[NF.NOUFU] - F, F, N[NF.MENJO_HOUTEI], N[NF.MENJO_SHINSEI],
                        N[NF.MENJO_3_4], N[NF.MENJO_1_2], N[NF.MENJO_1_4], N[NF.GAKUSEI],
                        N[NF.WAKAMONO],
                        1. - N[NF.NOUFU] - N[NF.MENJO_HOUTEI] - N[NF.MENJO_SHINSEI]
                        - N[NF.MENJO_3_4] - N[NF.MENJO_1_2] - N[NF.MENJO_1_4]
                        - N[NF.GAKUSEI] - N[NF.WAKAMONO]])
        # 港は %11.9e で書く（有効数字10桁）
        np.testing.assert_allclose(got, v, rtol=2e-9, atol=1e-9,
                                   err_msg="性%d 年度%d 年齢%d" % (f[0] and int(f[0]), y, x))
        worst = max(worst, float(np.max(np.abs(got - v))))
        n_rows += 1
    assert n_rows == 2 * 105 * 51
