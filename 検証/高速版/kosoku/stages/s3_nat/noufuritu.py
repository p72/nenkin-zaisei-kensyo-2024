# -*- coding: utf-8 -*-
"""第1号被保険者の納付率・免除の対象割合の将来推計（移植版 `noufuritu.c` 相当）
================================================================================
`Noufuritu[区分][y, x, 納付区分 0〜10]`（被保険者に対する割合。0 は計・未使用）と
`Noufuritu_Fuka[区分][y, x]`（付加年金の納付率）を作る。第3号は「全部納付」。

納付区分: 1 全額納付、2 4分の3免除、3 半額免除、4 4分の1免除、5 法定免除、
6 申請全額免除、7 学生納付特例、8 若年者納付猶予、9 産前産後免除、10 育児期間免除。
1〜4 が「保険料を納める区分」（納付率を持つ）、5〜10 が「納めない区分」。

年度ごとの手順（第1号、年度 y = 2022〜）
  1. 足元の対象割合を年齢上限で切る（若年者猶予は 50歳、ほかは 60歳）
  2. 2023年度以降: 法定免除と学生納付特例は人口の伸びで前年度から伸ばし、
     ほかの免除は前年度のまま。全額納付 = 1 − 免除の合計（`_taishou_hosei`）
  3. 女: 出生率 × 2/3 × 1/3 を各区分から産前産後免除へ移す。2026年度から育児期間免除
     （× 3/4。初年度は半分）。男: 妻の育児期間に合わせて夫も免除（× 4/3 の比）
  4. 全体の納付率を目標納付率（`mokuhyou_noufuritu_saishu.csv`）に合わせる
     （目標 ≤ 合計なら比で縮め、そうでなければ未納から引き上げる）
  5. 付加年金の納付率は「全額納付 × 納付率 ＋ 産休 ＋ 育休」を超えない
  6. 追納（過年度納付 1回 ＋ 追納 10回ぶんの率）で免除から納付へ戻す

港: nat/noufuritu.py:noufuritu
仕様: §4.2 ⑤、§6.2（`hw` の入力）
"""
from dataclasses import dataclass
import os

import numpy as np

from ...axis import YEARS, AGES
from ...options import options_of
from ...io_port import lines_of
from .inputs import MALE, FEMALE

__all__ = ["NoufuInputs", "read_noufu_inputs", "NoufuResult", "noufuritu",
           "N_KUBUN", "NOUFU", "MENJO_3_4", "MENJO_1_2", "MENJO_1_4", "MENJO_HOUTEI",
           "MENJO_SHINSEI", "GAKUSEI", "WAKAMONO", "SANKYU", "IKUKYU", "NOUFU_KUBUN"]

N_KUBUN = 11
(SUM, NOUFU, MENJO_3_4, MENJO_1_2, MENJO_1_4, MENJO_HOUTEI, MENJO_SHINSEI, GAKUSEI,
 WAKAMONO, SANKYU, IKUKYU) = range(N_KUBUN)
NOUFU_KUBUN = 5                       # 1〜4 が納める区分
AGE_MIN, AGE_MAX = 20, 70
NA = AGE_MAX - AGE_MIN + 1            # 51
A = slice(AGES.i(AGE_MIN), AGES.i(AGE_MAX) + 1)
EPSILON = 1e-14
_MAX_NENREI_BEFORE = (70, 70, 60, 60, 60, 60, 60, 60, 30, 60, 60)
_MAX_NENREI_AFTER = (70, 70, 60, 60, 60, 60, 60, 60, 50, 60, 60)
_MATERNITY_HOSEI = (0., 1., 1., 1., 1., 1., 1., 0., 1., 0., 0.)
_IKUKYU_HOSEI_M = (0., 1., 1., 1., 1., 1. / 4., 1., 0., 1., 0., 0.)
SEXES = (MALE, FEMALE)
_SHUBETU_1GOU = {MALE: 2, FEMALE: 5}


@dataclass(frozen=True)
class NoufuInputs:
    """足元の納付率・対象割合（性別 → (NA, …)）、追納率、目標納付率、付加、出生率。"""
    noufuritu0: dict         # sex → (NA, NOUFU_KUBUN)  納付区分 1〜4 の納付率
    taishou0: dict           # sex → (NA, N_KUBUN)      対象割合（1〜10。10 は 0）
    tuinou: dict             # sex → (3, NA, N_KUBUN)    [1] 過年度納付、[2] 追納
    fuka0: dict              # sex → (NA,)               付加年金の納付率（足元）
    mokuhyo: np.ndarray      # (YEARS.n,) 目標納付率
    maternity: np.ndarray    # (YEARS.n, NA, N_KUBUN) 出生率 × 2/3 × 区分の補正


def _rows(path, skip):
    L = [l for l in lines_of(path) if l.strip()]
    out = []
    for l in L[skip:]:
        f = [x.strip() for x in l.split(",")]
        try:
            out.append([float(x) for x in f if x != ""])
        except ValueError:
            continue
    return out


def read_noufu_inputs(kisoritu_dir, birth_file):
    """`noufu_menjo2022.csv` `tuinouritu2022.csv` `mokuhyou_noufuritu_saishu.csv`
    `fuka_noufuritu2022.csv` `birth_ratio_N.csv` を読む。港: nat/noufuritu.py:noufuritu"""
    p = lambda n: os.path.join(kisoritu_dir, n)          # noqa: E731
    noufuritu0, taishou0, tuinou, fuka0 = {}, {}, {}, {}
    rows = _rows(p("noufu_menjo2022.csv"), 2)
    for sex in SEXES:
        sh = _SHUBETU_1GOU[sex]
        n0 = np.zeros((NA, NOUFU_KUBUN))
        t0 = np.zeros((NA, N_KUBUN))
        for r in rows:
            if int(r[0]) != sh:
                continue
            i = int(r[1]) - AGE_MIN
            n0[i, 1:] = r[2:6]
            t0[i, 1:10] = r[6:15]
        noufuritu0[sex], taishou0[sex] = n0, t0
    rows = _rows(p("tuinouritu2022.csv"), 2)
    for sex in SEXES:
        sh = _SHUBETU_1GOU[sex]
        z = np.zeros((3, NA, N_KUBUN))
        for r in rows:
            if int(r[0]) != sh:
                continue
            for j in range(1, IKUKYU):
                for c in (1, 2):
                    z[c, :, j] = r[(j - 1) * 2 + c]
        tuinou[sex] = z
    mok = YEARS.zeros()
    for r in _rows(p("mokuhyou_noufuritu_saishu.csv"), 1):
        y = int(r[0])
        if YEARS.contains(y):
            mok[YEARS.i(y)] = r[1]
    rows = _rows(p("fuka_noufuritu2022.csv"), 1)
    for sex in SEXES:
        sh = _SHUBETU_1GOU[sex]
        f0 = np.zeros(NA)
        for r in rows:
            if int(r[0]) == sh:
                f0[int(r[1]) - AGE_MIN] = r[2]
        fuka0[sex] = f0
    mat = np.zeros((YEARS.n, NA, N_KUBUN))
    birth = np.zeros((YEARS.n, NA))
    for r in _rows(birth_file, 2):
        age = int(r[0])
        if not (AGE_MIN <= age < AGE_MAX):
            continue
        for k, v in enumerate(r[1:]):
            y = 2020 + k                                 # 港: SHONENDO 起点
            if YEARS.contains(y):
                birth[YEARS.i(y), age - AGE_MIN] = v * 2. / 3.
    for j in range(1, N_KUBUN):
        mat[:, :, j] = birth * _MATERNITY_HOSEI[j]
    return NoufuInputs(noufuritu0, taishou0, tuinou, fuka0, mok, mat)


@dataclass
class NoufuResult:
    noufuritu: dict          # sex → (YEARS.n, AGES.n, N_KUBUN)  第1号
    noufuritu_fuka: dict     # sex → (YEARS.n, AGES.n)
    noufuritu_3gou: np.ndarray   # (YEARS.n, AGES.n, N_KUBUN)  第3号（性別によらない）
    sankyu_sum: np.ndarray   # (YEARS.n,) 産前産後免除の人数（女）
    ikukyu_sum: np.ndarray   # (YEARS.n,) 育児期間免除の人数（女＋男）


def _max_nenrei(pol, year):
    henko = pol.get("kokunen.years.wakamono_henko_nendo")
    return np.array(_MAX_NENREI_BEFORE if year < henko else _MAX_NENREI_AFTER)


def _zengaku_noufu(tw):
    """全額納付 = 1 − 免除の合計（区分 2〜10）。負なら落とす。"""
    tw[:, NOUFU] = 1. - tw[:, 2:].sum(axis=1)
    if (tw[:, NOUFU] < 0.).any():
        raise ValueError("全額納付の対象割合が負")


def _taishou_hosei(tw, tw_zen, hiho, hiho_zen, jinko, jinko_zen, part_gakusei_skip):
    """法定免除・学生は人口の伸びで伸ばし、ほかは前年度のまま。合計が1を超えたら
    法定と学生から削る。港: nat/noufuritu.py:noufuritu（`_taishou_hosei`）"""
    growth = np.divide(jinko, jinko_zen, out=np.zeros(NA), where=jinko_zen != 0.)
    inv = np.divide(1., hiho, out=np.zeros(NA), where=hiho != 0.)
    for j in range(1, N_KUBUN):
        if j == MENJO_HOUTEI or (j == GAKUSEI and not part_gakusei_skip):
            tw[:, j] = tw_zen[:, j] * hiho_zen * growth * inv
        elif j != NOUFU:
            tw[:, j] = tw_zen[:, j]
    menjo_sum = tw[:, 2:].sum(axis=1)
    over = menjo_sum > 1.
    if over.any():
        r = (menjo_sum - 1. + EPSILON) / (tw[:, MENJO_HOUTEI] + tw[:, GAKUSEI])
        tw[over, MENJO_HOUTEI] *= 1. - r[over]
        tw[over, GAKUSEI] *= 1. - r[over]
    _zengaku_noufu(tw)


def _sankyu(tw, mat, hiho):
    """産前産後免除へ移す（各区分 × 出生率 × 1/3）。戻り値は人数。"""
    move = tw * mat / 3.
    move[:, SANKYU] = 0.
    move[:, IKUKYU] = 0.
    ninzu = (hiho[:, None] * move).sum()
    tw[:, SANKYU] += move.sum(axis=1)
    tw -= move
    return ninzu


def _ikukyu_f(tw, tw_mae, mat, hiho, eikyo):
    """育児期間免除（女）。元は産前産後を引く前の割合。戻り値 (人数の年齢別, 合計)。"""
    move = tw_mae * mat * 3. / 4. * eikyo
    move[:, SANKYU] = 0.
    move[:, IKUKYU] = 0.
    hiho_ikukyu = (hiho[:, None] * move).sum(axis=1)
    tw[:, IKUKYU] += move.sum(axis=1)
    tw -= move
    return hiho_ikukyu, hiho_ikukyu.sum()


def _ikukyu_m(tw, hiho, hiho_ikukyu_f):
    """育児期間免除（男）。妻の育児期間の人数 × 4/3 を夫の被保険者数で割った比を掛ける。
    原本は 0 割りを見ない（NaN になる）。高速版は 0 で割るところを 0 にする。"""
    hosei = np.array(_IKUKYU_HOSEI_M)
    w = tw * hosei[None, :]
    w[:, SANKYU] = 0.
    w[:, IKUKYU] = 0.
    hiho_ninzu = (hiho[:, None] * w).sum(axis=1)
    ratio = np.divide(hiho_ikukyu_f * 4. / 3., hiho_ninzu, out=np.zeros(NA),
                      where=hiho_ninzu != 0.)
    move = w * ratio[:, None]
    ninzu = (hiho[:, None] * move).sum()
    tw[:, IKUKYU] += move.sum(axis=1)
    tw -= move
    return ninzu


def _noufu_hosei(mokuhyo, nr, tw, hiho, max_nenrei, max_nenrei_op):
    """全体の納付率を目標に合わせる（両性まとめて）。"""
    ages = np.arange(AGE_MIN, AGE_MAX + 1)
    noufu_taishou = gokei = non_gokei = 0.
    for sex in SEXES:
        for k in range(1, NOUFU_KUBUN):
            m = ages <= max_nenrei[k]
            t = tw[sex][m, k] * hiho[sex][m]
            noufu_taishou += t.sum()
            gokei += (nr[sex][m, k] * t).sum()
            non_gokei += ((1. - nr[sex][m, k]) * t).sum()
    target = mokuhyo * noufu_taishou
    if target <= gokei:
        r = target / gokei if gokei != 0. else 0.
        for sex in SEXES:
            for k in range(1, NOUFU_KUBUN):
                m = ages <= max_nenrei_op[k]
                nr[sex][m, k] *= r
    else:
        hikiage = (target - gokei) / non_gokei if non_gokei != 0. else 0.
        for sex in SEXES:
            for k in range(1, NOUFU_KUBUN):
                m = ages <= max_nenrei_op[k]
                base = hiho[sex][m] * tw[sex][m, k]
                ninzu = base * nr[sex][m, k] + base * (1. - nr[sex][m, k]) * hikiage
                nr[sex][m, k] = np.divide(ninzu, base, out=np.zeros(ninzu.shape), where=base != 0.)


def noufuritu(pol, inputs, sotowaku, first_year=2022, ikukyu_nendo=2026, nendo_jisseki=2022):
    """納付率と免除の対象割合を全年度ぶん作る。"""
    n_first = pol.get("kokunen.years.suikei_shonendo")          # 2021
    ikukyu_nendo = pol.get("kokunen.years.ikukyu_henko_nendo")
    ikukyu_ritu = pol.get("kokunen.years.ikukyu_henko_ritu")
    nendo_jisseki = pol.get("kokunen.years.nendo_jisseki")
    wak_nendo = pol.get("kokunen.years.wakamono_henko_nendo")
    wak_ritu = pol.get("kokunen.years.wakamono_henko_ritu")

    # 適用拡大（レバー kakudai。港の Part）: 目標納付率の上乗せと、最大の案では学生免除を 2 年据え置く
    PT = pol.get("kokunen.part")
    kakudai = options_of(pol).kakudai
    part_year = int(PT["year"])
    mokuhyo = inputs.mokuhyo.copy()
    if kakudai:
        mokuhyo[YEARS.i(part_year):] += float(PT["mokuhyo_add"][str(kakudai)])
    gakusei_skip_mode = int(PT["gakusei_skip_mode"])

    out = {s: np.zeros((YEARS.n, AGES.n, N_KUBUN)) for s in SEXES}
    fuka = {s: np.zeros((YEARS.n, AGES.n)) for s in SEXES}
    for s in SEXES:
        fuka[s][:, A] = inputs.fuka0[s][None, :]
    sankyu_sum = YEARS.zeros()
    ikukyu_sum = YEARS.zeros()

    # 第3号: 60歳まで全部納付
    g3 = np.zeros((YEARS.n, AGES.n, N_KUBUN))
    g3[:, AGES.i(AGE_MIN):AGES.i(60) + 1, NOUFU] = 1.

    hiho = {s: sotowaku.gou1[s][YEARS.i(n_first), A].copy() for s in SEXES}
    jinko = {s: sotowaku.jinko[s][YEARS.i(n_first), A].copy() for s in SEXES}
    tw_zen = {s: np.zeros((NA, N_KUBUN)) for s in SEXES}
    hiho_ikukyu_f = np.zeros(NA)
    ages = np.arange(AGE_MIN, AGE_MAX + 1)

    for year in range(n_first + 1, YEARS.last + 1):
        yi = YEARS.i(year)
        max_n = _max_nenrei(pol, year)
        max_op = max_n                                  # 45年化なし
        hiho_zen = {s: hiho[s] for s in SEXES}
        jinko_zen = {s: jinko[s] for s in SEXES}
        hiho, jinko, tw_mae, nr = {}, {}, {}, {}
        for s in SEXES:
            g1 = sotowaku.gou1[s]
            h = np.empty(NA)
            h[0] = g1[yi, AGES.i(AGE_MIN)] / 2.
            h[1:] = (g1[yi - 1, AGES.i(AGE_MIN):AGES.i(AGE_MAX)] + g1[yi, A][1:]) / 2.
            hiho[s] = h
            jinko[s] = sotowaku.jinko[s][yi, A].copy()
            tw = inputs.taishou0[s].copy()
            for j in range(1, N_KUBUN):
                tw[ages > max_op[j], j] = 0.
            if year == wak_nendo:
                lo, hi = _MAX_NENREI_BEFORE[WAKAMONO], _MAX_NENREI_AFTER[WAKAMONO]
                tw[(ages >= lo) & (ages < hi), WAKAMONO] *= wak_ritu
            tw_mae[s] = tw
            n0 = inputs.noufuritu0[s].copy()
            for k in range(1, NOUFU_KUBUN):
                n0[ages > max_op[k], k] = 0.
            nr[s] = n0

        tw = {}
        for s in (FEMALE, MALE):                        # 女 → 男の順（育休の受け渡し）
            if year > nendo_jisseki:
                skip = kakudai == gakusei_skip_mode and part_year <= year <= part_year + 1
                _taishou_hosei(tw_mae[s], tw_zen[s], hiho[s], hiho_zen[s], jinko[s],
                               jinko_zen[s], part_gakusei_skip=skip)
            tw_zen[s] = tw_mae[s].copy()
            tw[s] = tw_mae[s].copy()
            if s == FEMALE:
                sankyu_sum[yi] = _sankyu(tw[s], inputs.maternity[yi], hiho[s])
                if year >= ikukyu_nendo:
                    eikyo = ikukyu_ritu if year == ikukyu_nendo else 1.
                    hiho_ikukyu_f, ikukyu_sum[yi] = _ikukyu_f(tw[s], tw_mae[s],
                                                              inputs.maternity[yi],
                                                              hiho[s], eikyo)
            elif year >= ikukyu_nendo:
                ikukyu_sum[yi] += _ikukyu_m(tw[s], hiho[s], hiho_ikukyu_f)

        _noufu_hosei(mokuhyo[yi], nr, tw, hiho, max_n, max_op)

        for s in SEXES:
            # 付加年金の納付率の上限
            cap = tw[s][:, NOUFU] * nr[s][:, NOUFU] + tw[s][:, SANKYU] + tw[s][:, IKUKYU]
            f = fuka[s][yi, A]
            fuka[s][yi, A] = np.where(cap < f, cap, f)
            # 追納（過年度納付 1回 ＋ 追納 10回。足す順は港のまま 11回）
            z = inputs.tuinou[s]
            tui = np.zeros((NA, N_KUBUN))
            for j in range(1, N_KUBUN):
                if j in (NOUFU, SANKYU, IKUKYU):
                    continue
                v = np.zeros(NA)
                for c in range(0, 11):
                    v = v + z[1 if c == 0 else 2][:, j]
                tui[:, j] = v * tw[s][:, j]
            res = np.zeros((NA, N_KUBUN))
            hiho_ritu = tw[s][:, :NOUFU_KUBUN] * nr[s]  # (NA, 5) ただし列 0 は無視
            for k in range(1, NOUFU_KUBUN):
                v = hiho_ritu[:, k].copy()
                if k == NOUFU:
                    for j in range(1, N_KUBUN):
                        if j not in (NOUFU, SANKYU, IKUKYU):
                            v += tui[:, j]
                    v += tw[s][:, SANKYU]
                    if year >= ikukyu_nendo:
                        v += tw[s][:, IKUKYU]
                else:
                    v -= tui[:, k]
                res[:, k] = v
            for j in range(NOUFU_KUBUN, N_KUBUN):
                v = tw[s][:, j].copy()
                if j not in (SANKYU, IKUKYU):
                    v -= tui[:, j]
                res[:, j] = v
            out[s][yi, A] = res
    return NoufuResult(out, fuka, g3, sankyu_sum, ikukyu_sum)
