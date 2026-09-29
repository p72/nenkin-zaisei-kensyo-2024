# -*- coding: utf-8 -*-
"""③の基礎率 — 読み込みと将来への延ばし方（移植版 `kiso.c` 相当）
====================================================================
基礎率は**入力**（`nat/base_data/kisoritu/`）。ここでやるのは読むことと、
足元の値を将来に延ばすことだけ（率の導出はしない。`計画.md`「やらないこと」）。

延ばし方（港: nat/kiso.py:kiso）
  脱退力（死亡）  足元 × 死亡率[y, x] ／ 死亡率[2021, x]（1年）。総合 = 総合0 − 死亡0 + 死亡[y]。
                  65歳以上（第3号は60歳以上）は 1
  失権率（老齢・障害） 足元 × 死亡率[y, x] ／ 2019〜2021の平均。105〜114歳は104歳の比、115歳は 1。
                  2070年度より先は据え置き。1 を超えたら 1
  遺族の発生割合  足元 × 有配偶率[y, x] ／ 有配偶率[2021, x]
  夫の失権率      13年かけて「2歳若い妻の失権率」へ線形に寄せる
  支給率          老齢は足元を全年度に（労福下支えだけ1年1歳ずらす）。旧法は構造体ごと
                  1年1歳ずらし60歳は 1。障害は生年（男 1953〜／女 1958〜）で経過措置の率に
                  差し替え、96歳以上（2021年度で95歳超）は1年1歳ずらす。旧法障害は65歳で足元に戻す
  ほかは足元の値を全年度に写す

区分（号・性）ごとに `Rates` を1つ持つ。第3号は同じ性の第1号の率を基に、脱退力・
老齢支給率の納付分・一部繰上げの納付分・（女は）夫の発生割合だけ差し替える
（港は種別 2→3→5→6 の順に上書きしてグローバルを共有する。ここでは明示する）。

港: nat/kiso.py:kiso
仕様: §4.2、§5.2、§5.2.1、§5.3
"""
from dataclasses import dataclass, field
import os

import numpy as np

from ...axis import YEARS, AGES, COHORTS
from ...io_port import lines_of
from .inputs import MALE, FEMALE
from .layouts import ROREI, ROREI_KYU, MENJO_DANKAI, KOKKO_KUBUN

__all__ = ["Rates", "read_rates", "read_rate_file"]

AGE_MIN, AGE_MAX = 20, 70
ROREI_MIN, ROREI_MAX = 60, 115
KURIAGE_N = 11
TOKYU_N = 3
_FILE_NO = {"dattai": "101", "rorei": "103", "shogai": "104", "izoku": "105", "ichiji": "106",
            "tokyu": "107", "kakyu": "108", "sokan": "109", "shk_rorei": "110",
            "shk_shogai": "111", "shk_izoku": "112", "shikyu": "113", "ichibu": "114"}
_SEX_TAG = {MALE: "m", FEMALE: "f"}


def read_rate_file(path):
    """`(tag, key, 値…)` の行を {tag: {key: [値…]}} に。見出し行は捨てる。"""
    out = {}
    for l in lines_of(path):
        f = [x.strip() for x in l.split(",")]
        try:
            vals = [float(x) for x in f if x != ""]
        except ValueError:
            continue
        if len(vals) < 2:
            continue
        tag = int(vals[0])
        out.setdefault(tag, {})[int(vals[1])] = vals[2:]
    return out


def _by_age(table, tag, lo, hi, col=0):
    """tag の行を年齢 lo〜hi で AGES の軸に置く。"""
    a = np.zeros(AGES.n)
    rows = table.get(tag, {})
    for age in range(lo, hi + 1):
        if age not in rows:
            raise ValueError("基礎率 %d の %d 歳が無い" % (tag, age))
        a[AGES.i(age)] = rows[age][col]
    return a


def _all_years(row):
    """年齢の配列を全年度に写す → (YEARS.n, AGES.n)。"""
    return np.repeat(row[None, :], YEARS.n, axis=0)


@dataclass
class Rates:
    sex: int
    gou: int
    lifetable_last: int
    dattai_gokei: np.ndarray = None
    dattai_shibou: np.ndarray = None
    saikanyuritu: np.ndarray = None
    hassei_rorei: np.ndarray = None          # (YEARS.n, KURIAGE_N)
    hasseiryoku_shogai: np.ndarray = None
    hassei_20mae: np.ndarray = None
    hassei_tuma: np.ndarray = None
    hassei_ko: np.ndarray = None
    hassei_kafu: np.ndarray = None
    hassei_otto: np.ndarray = None
    hassei_shibou: np.ndarray = None
    tokyu_ippan: np.ndarray = None           # (YEARS.n, TOKYU_N)
    tokyu_20mae: np.ndarray = None
    kakyu_ippan_12: np.ndarray = None
    kakyu_ippan_3: np.ndarray = None
    kakyu_20mae_12: np.ndarray = None
    kakyu_20mae_3: np.ndarray = None
    kakyu_tuma_12: np.ndarray = None
    kakyu_tuma_3: np.ndarray = None
    kakyu_otto_12: np.ndarray = None
    kakyu_otto_3: np.ndarray = None
    kakyu_ko_12: np.ndarray = None
    kakyu_ko_3: np.ndarray = None
    sokan_tuma: np.ndarray = None
    sokan_otto: np.ndarray = None
    sokan_ko: np.ndarray = None
    sokan_kafu: np.ndarray = None
    shikken_rorei: np.ndarray = None
    shikken_ippan: np.ndarray = None
    shikken_20mae: np.ndarray = None
    shikken_tuma: np.ndarray = None
    shikken_otto: np.ndarray = None
    shikken_ko: np.ndarray = None
    shikken_kafu: np.ndarray = None
    shikyuritu_rorei: np.ndarray = None      # (YEARS.n, AGES.n, ROREI.n)
    shikyuritu_rorei_kyu: np.ndarray = None  # (YEARS.n, AGES.n, ROREI_KYU.n)
    shikyuritu_turo_kyu: np.ndarray = None
    shikyuritu_gonen: np.ndarray = None      # (YEARS.n, AGES.n)
    shikyuritu_shogai_ippan: np.ndarray = None   # (YEARS.n, AGES.n, TOKYU_N)
    shikyuritu_shogai_20mae: np.ndarray = None
    shikyuritu_shogai_kyu: np.ndarray = None
    shikyuritu_tuma: np.ndarray = None       # (YEARS.n,)
    shikyuritu_otto: np.ndarray = None
    shikyuritu_ko: np.ndarray = None
    shikyuritu_kafu: np.ndarray = None       # (YEARS.n, AGES.n)  60〜64歳
    kakudai_ichibu: dict = field(default_factory=dict)   # 生年度 → (KURIAGE_N, ROREI.n)
    waribiki_n: np.ndarray = None            # (5 繰下げ年齢 66〜70, 10 年度)
    waribiki_b: np.ndarray = None
    kyufu_ritu: dict = field(default_factory=dict)       # (受給年齢, 生年度) → 率

    def copy(self):
        import copy
        return copy.deepcopy(self)


def _project_with_q(base, q, lt_last, ages_lo, ages_hi, three_year, sex_q):
    """失権率・死亡脱退力を死亡率で延ばす。`base[AGES.n]`（足元）。"""
    out = np.zeros((YEARS.n, AGES.n))
    y0 = YEARS.i(2021)
    lo, hi = AGES.i(ages_lo), AGES.i(min(ages_hi, 104)) + 1
    if three_year:
        den = (sex_q[YEARS.i(2019), lo:hi] + sex_q[YEARS.i(2020), lo:hi]
               + sex_q[YEARS.i(2021), lo:hi]) / 3.
    else:
        den = sex_q[YEARS.i(2021), lo:hi]
    for y in range(2021, lt_last + 1):
        yi = YEARS.i(y)
        out[yi, lo:hi] = base[lo:hi] * sex_q[yi, lo:hi] / den
        if ages_hi > 104:
            r = out[yi, AGES.i(104)] / base[AGES.i(104)] if base[AGES.i(104)] != 0. else 0.
            for age in range(105, ages_hi):
                out[yi, AGES.i(age)] = base[AGES.i(age)] * r
            out[yi, AGES.i(ages_hi)] = 1.
    out[YEARS.i(lt_last) + 1:] = out[YEARS.i(lt_last)]
    return out


def _rorei_shikyu(table, tag, noufu_only=False, base=None):
    """301 老齢基礎の支給率 → (YEARS.n, AGES.n, ROREI.n)。労福下支えは1年1歳ずらす。"""
    y0 = YEARS.i(2021)
    r0 = np.zeros((AGES.n, ROREI.n)) if base is None else base[y0].copy()
    rows = table[tag]
    for age in range(ROREI_MIN, ROREI_MAX + 1):
        v = rows[age]
        rec = r0[AGES.i(age)]
        if noufu_only:
            rec[ROREI.i("noufu")] = v[0]
            continue
        rec[ROREI.i("ninzu")] = v[0]
        rec[ROREI.i("noufu")] = v[1]
        for d in range(MENJO_DANKAI):
            for k in range(KOKKO_KUBUN):
                rec[ROREI.i("menjo[%d][%d]" % (d, k))] = v[2] if d <= 1 else v[3]
        rec[ROREI.i("rofuku_shitasasae")] = v[4]
        rec[ROREI.i("fuka")] = v[5]
    out = np.zeros((YEARS.n, AGES.n, ROREI.n))
    out[y0] = r0
    i_rf = ROREI.i("rofuku_shitasasae")
    for y in range(2022, YEARS.last + 1):
        yi = YEARS.i(y)
        out[yi] = r0
        out[yi, AGES.i(ROREI_MIN + 1):AGES.i(ROREI_MAX) + 1, i_rf] = \
            out[yi - 1, AGES.i(ROREI_MIN):AGES.i(ROREI_MAX), i_rf]
        out[yi, AGES.i(ROREI_MIN), i_rf] = 1.
    return out


def _kyu_shikyu(table, tag):
    """302/303 旧法の支給率。構造体ごと1年1歳ずらし、60歳は全部 1。"""
    y0 = YEARS.i(2021)
    out = np.zeros((YEARS.n, AGES.n, ROREI_KYU.n))
    for age in range(ROREI_MIN, ROREI_MAX + 1):
        out[y0, AGES.i(age)] = table[tag][age][:7]
    lo, hi = AGES.i(ROREI_MIN), AGES.i(ROREI_MAX)
    for y in range(2022, YEARS.last + 1):
        yi = YEARS.i(y)
        out[yi, lo + 1:hi + 1] = out[yi - 1, lo:hi]
        out[yi, lo] = 1.
    return out


def _gonen_shikyu(table):
    y0 = YEARS.i(2021)
    out = np.zeros((YEARS.n, AGES.n))
    for age in range(ROREI_MIN, ROREI_MAX + 1):
        out[y0, AGES.i(age)] = table[304][age][0]
    lo, hi = AGES.i(ROREI_MIN), AGES.i(ROREI_MAX)
    for y in range(2022, YEARS.last + 1):
        yi = YEARS.i(y)
        out[yi, lo + 1:hi + 1] = out[yi - 1, lo:hi]
        out[yi, lo] = 1.
    return out


def _shogai_shikyu(table, tag, sex, y_first=2021):
    """305/306 障害の支給率。足元は 2020年度に入る。生年で経過措置に差し替え。
    `y_first` は推計初年度（その年度に生年度の軸の先頭が何歳かで「ずらす」境目を決める）。"""
    y0 = YEARS.i(2020)
    base = np.zeros((AGES.n, TOKYU_N))
    keinen = np.zeros((AGES.n, TOKYU_N))
    for age in range(20, 115 + 1):
        v = table[tag][age]
        base[AGES.i(age), 1], base[AGES.i(age), 2] = v[2], v[3]
        keinen[AGES.i(age), 1], keinen[AGES.i(age), 2] = v[0], v[1]
    if sex == MALE:
        kk = ((1953, 1954, 60), (1955, 1956, 61), (1957, 1958, 62), (1959, 1960, 63))
        ijou = 1961
    else:
        kk = ((1958, 1959, 60), (1960, 1961, 61), (1962, 1963, 62), (1964, 1965, 63))
        ijou = 1966
    out = np.zeros((YEARS.n, AGES.n, TOKYU_N))
    cut = y_first - COHORTS.first           # 95歳（港: 推計初年度 − 生年度の先頭）
    for y in range(2020, YEARS.last + 1):
        yi = YEARS.i(y)
        for age in range(20, cut + 1):
            ai = AGES.i(age)
            out[yi, ai] = base[ai]
            seinen = y - age
            hit = any((seinen in (a, b)) and 60 <= age <= ue for a, b, ue in kk)
            if seinen >= ijou and 60 <= age <= 64:
                hit = True
            if hit:
                out[yi, ai] = keinen[ai]
        for age in range(cut + 1, 115 + 1):
            ai = AGES.i(age)
            if y == 2020:
                out[yi, ai] = base[ai]
            elif y == 2021:
                out[yi, ai] = out[yi - 1, ai]
            else:
                out[yi, ai] = out[yi - 1, ai - 1]
    return out


def _shogai_kyu_shikyu(table):
    """307 旧法障害。1年1歳ずらし、20歳は 1、65歳だけ足元に戻す。"""
    y0 = YEARS.i(2020)
    out = np.zeros((YEARS.n, AGES.n, TOKYU_N))
    for age in range(20, 115 + 1):
        v = table[307][age]
        out[y0, AGES.i(age), 1], out[y0, AGES.i(age), 2] = v[0], v[1]
    for y in range(2021, YEARS.last + 1):
        yi = YEARS.i(y)
        for age in range(20, 115 + 1):
            ai = AGES.i(age)
            if age == 20:
                out[yi, ai, 1:] = 1.
            elif age == 65:
                out[yi, ai] = out[y0, ai]
            else:
                out[yi, ai] = out[yi - 1, ai - 1]
    return out


def _read_ichibu(path, noufu_only=False, base=None):
    """114 一部繰上げの適用拡大。生年度 1957〜1961 × 受給年齢 60〜64 の係数。"""
    out = {} if base is None else {k: v.copy() for k, v in base.items()}
    for l in lines_of(path):
        f = [x.strip() for x in l.split(",")]
        try:
            vals = [float(x) for x in f if x != ""]
        except ValueError:
            continue
        if len(vals) < 3:
            continue
        cohort, j_age = int(vals[0]), int(vals[1])
        if not (60 <= j_age <= 64):
            continue
        row = out.setdefault(cohort, np.ones((KURIAGE_N, ROREI.n)))
        rec = row[j_age - 60]
        rec[ROREI.i("noufu")] = vals[2]
        if not noufu_only:
            rec[ROREI.i("menjo[1][1]")] = vals[3]
            rec[ROREI.i("menjo[2][1]")] = vals[4]
            rec[ROREI.i("menjo[3][1]")] = vals[5]
            rec[ROREI.i("menjo[4][1]")] = vals[6]
            rec[ROREI.i("fuka")] = vals[7]
    return out


def _read_waribiki(path, first_year, last_year):
    """繰下げ移行措置の係数（人数・年金額）。行は (性, 繰下げ年齢 66〜70, 年度, 人数の係数, 額の係数)。"""
    n_y = last_year - first_year + 1
    n = np.ones((5, n_y))
    b = np.ones((5, n_y))
    for l in lines_of(path):
        f = [x.strip() for x in l.split(",")]
        try:
            vals = [float(x) for x in f if x != ""]
        except ValueError:
            continue
        if len(vals) < 5 or int(vals[0]) != 0:          # 男女同値なので 0 の行だけ
            continue
        j, y = int(vals[1]), int(vals[2])
        if 66 <= j <= 70 and first_year <= y <= last_year:
            n[j - 66, y - first_year] = vals[3]
            b[j - 66, y - first_year] = vals[4]
    return n, b


def _read_kyufu(p1, p2, henkou_seinendo, kyufu2_cohort):
    """給付率（繰上げ・繰下げ）。生年度 1941 未満は列 0、以降は列 1。1962年度生以降は2本目。"""
    def one(path):
        t = np.zeros((KURIAGE_N, 2))
        for l in lines_of(path):
            f = [x.strip() for x in l.split(",")]
            try:
                vals = [float(x) for x in f if x != ""]
            except ValueError:
                continue
            if len(vals) < 3:
                continue
            c, j = int(vals[0]), int(vals[1])
            if c in (0, 1) and 60 <= j <= 70:
                t[j - 60, c] = vals[2]
        return t
    k1, k2 = one(p1), one(p2)
    out = {}
    for cohort in range(1951, 2066):
        col = 0 if cohort < henkou_seinendo else 1
        t = k2 if cohort >= kyufu2_cohort else k1
        for j in range(KURIAGE_N):
            out[(60 + j, cohort)] = t[j, col]
    return out


def read_rates(pol, kisoritu_dir, sex, gou, lifetable, yuhaigu, base=None):
    """区分 (号, 性) の `Rates`。第3号は `base`（同じ性の第1号）を基に差し替える。"""
    tag = "%d%s" % (gou, _SEX_TAG[sex])
    p = lambda k: os.path.join(kisoritu_dir, "%s_%s_%s.csv" % (_FILE_NO[k], tag, {
        "dattai": "dattairyoku", "rorei": "rorei_hasseiwariai", "shogai": "shogai_hasseiryoku",
        "izoku": "izoku_hasseiwariai", "ichiji": "ichijikin_hasseiwariai", "tokyu": "tokyuwariai",
        "kakyu": "kakyuwariai", "sokan": "nenreisokan", "shk_rorei": "rorei_shikkenritsu",
        "shk_shogai": "shogai_shikkenritsu", "shk_izoku": "izoku_shikkenritsu",
        "shikyu": "shikyuritsu", "ichibu": "ichibu"}[k]))                       # noqa: E731
    q = lifetable.q[sex]
    lt_last = lifetable.last
    R = base.copy() if base is not None else Rates(sex, gou, lt_last)
    R.sex, R.gou = sex, gou
    y0 = YEARS.i(2021)

    # ---- 脱退力 ----
    t = read_rate_file(p("dattai"))
    g0 = _by_age(t, 1, AGE_MIN, AGE_MAX)
    s0 = _by_age(t, 2, AGE_MIN, AGE_MAX)
    R.dattai_shibou = _project_with_q(s0, q, lt_last, AGE_MIN, AGE_MAX, False, q)
    R.dattai_shibou[YEARS.i(2020)] = s0
    R.dattai_gokei = g0[None, :] - s0[None, :] + R.dattai_shibou
    R.dattai_gokei[YEARS.i(2020)] = g0
    ages = AGES.labels()
    stop = 60 if gou == 3 else 65
    m = (ages >= stop) & (ages <= AGE_MAX)
    R.dattai_gokei[YEARS.i(2021):, m] = 1.
    R.saikanyuritu = np.zeros((YEARS.n, AGES.n))
    if gou == 3:
        # 第3号は同じ性の第1号の率を基に、老齢の支給率の納付分と一部繰上げの納付分だけ差し替え
        t = read_rate_file(p("shikyu"))
        R.shikyuritu_rorei = _rorei_shikyu(t, 301, noufu_only=True, base=base.shikyuritu_rorei)
        R.kakudai_ichibu = _read_ichibu(p("ichibu"), noufu_only=True, base=base.kakudai_ichibu)
        R.hassei_shibou = np.zeros((YEARS.n, AGES.n))
        if sex == FEMALE:
            t = read_rate_file(p("izoku"))
            o0 = _by_age(t, 7, AGE_MIN, AGE_MAX)
            yh = yuhaigu[FEMALE]
            with np.errstate(divide="ignore", invalid="ignore"):
                growth = np.where(yh[y0][None, :] != 0., yh / yh[y0][None, :], 0.)
            R.hassei_otto = o0[None, :] * growth
        return R

    # ---- 発生割合 ----
    t = read_rate_file(p("rorei"))
    hr = np.zeros(KURIAGE_N)
    for j in range(KURIAGE_N):
        hr[j] = t[4][60 + j][0]
    R.hassei_rorei = np.repeat(hr[None, :], YEARS.n, axis=0)
    t = read_rate_file(p("shogai"))
    R.hasseiryoku_shogai = _all_years(_by_age(t, 5, AGE_MIN, AGE_MAX))
    R.hassei_20mae = _all_years(_by_age(t, 6, AGE_MIN, AGE_MAX))
    t = read_rate_file(p("izoku"))
    yh = yuhaigu[sex]
    with np.errstate(divide="ignore", invalid="ignore"):
        growth = np.where(yh[y0][None, :] != 0., yh / yh[y0][None, :], 0.)
    zero = np.zeros((YEARS.n, AGES.n))
    if sex == MALE:
        R.hassei_tuma = _by_age(t, 7, AGE_MIN, AGE_MAX)[None, :] * growth
        R.hassei_ko = _by_age(t, 8, AGE_MIN, AGE_MAX)[None, :] * growth
        kafu = _by_age(t, 9, AGE_MIN, AGE_MAX)[None, :] * growth
        tanshuku = pol.get("kokunen.years.tanshuku_nendo")
        for y in range(YEARS.first, tanshuku):
            kafu[YEARS.i(y), ages <= 44] = 0.
        R.hassei_kafu = kafu
        R.hassei_otto = zero.copy()
    else:
        R.hassei_otto = _by_age(t, 7, AGE_MIN, AGE_MAX)[None, :] * growth
        R.hassei_tuma = zero.copy()
        R.hassei_ko = zero.copy()
        R.hassei_kafu = zero.copy()
    t = read_rate_file(p("ichiji"))
    R.hassei_shibou = _all_years(_by_age(t, 10, AGE_MIN, AGE_MAX))

    # ---- 等級・加算・相関 ----
    # 107 は `(11, 値)` `(12, 値)` の2行（等級の割合）
    v11 = _first_value(p("tokyu"), 11)
    v12 = _first_value(p("tokyu"), 12)
    R.tokyu_ippan = np.repeat(np.array([[0., v11, 1. - v11]]), YEARS.n, axis=0)
    R.tokyu_20mae = np.repeat(np.array([[0., v12, 1. - v12]]), YEARS.n, axis=0)
    t = read_rate_file(p("kakyu"))
    R.kakyu_ippan_12 = _all_years(_by_age(t, 13, 20, 115))
    R.kakyu_ippan_3 = _all_years(_by_age(t, 14, 20, 115))
    R.kakyu_20mae_12 = _all_years(_by_age(t, 15, 20, 115))
    R.kakyu_20mae_3 = _all_years(_by_age(t, 16, 20, 115))
    if sex == MALE:
        R.kakyu_tuma_12 = _all_years(_by_age(t, 17, 16, 115))
        R.kakyu_tuma_3 = _all_years(_by_age(t, 18, 16, 115))
        R.kakyu_ko_12 = _all_years(_by_age(t, 19, 0, 19))
        R.kakyu_ko_3 = _all_years(_by_age(t, 20, 0, 19))
        R.kakyu_otto_12 = zero.copy()
        R.kakyu_otto_3 = zero.copy()
    else:
        R.kakyu_otto_12 = _all_years(_by_age(t, 17, 18, 115))
        R.kakyu_otto_3 = _all_years(_by_age(t, 18, 18, 115))
        R.kakyu_tuma_12 = zero.copy()
        R.kakyu_tuma_3 = zero.copy()
        R.kakyu_ko_12 = zero.copy()
        R.kakyu_ko_3 = zero.copy()
    t = read_rate_file(p("sokan"))
    if sex == MALE:
        R.sokan_tuma = _all_years(_by_age(t, 21, AGE_MIN, AGE_MAX))
        R.sokan_ko = _all_years(_by_age(t, 22, AGE_MIN, AGE_MAX))
        R.sokan_kafu = _all_years(_by_age(t, 23, AGE_MIN, AGE_MAX))
        R.sokan_otto = zero.copy()
    else:
        R.sokan_otto = _all_years(_by_age(t, 21, AGE_MIN, AGE_MAX))
        R.sokan_tuma = zero.copy()
        R.sokan_ko = zero.copy()
        R.sokan_kafu = zero.copy()

    # ---- 失権率 ----
    t = read_rate_file(p("shk_rorei"))
    R.shikken_rorei = np.minimum(_project_with_q(_by_age(t, 24, AGE_MIN, 115), q, lt_last,
                                                 AGE_MIN, 115, True, q), 1.)
    t = read_rate_file(p("shk_shogai"))
    R.shikken_ippan = np.minimum(_project_with_q(_by_age(t, 25, 20, 115), q, lt_last,
                                                 20, 115, True, q), 1.)
    R.shikken_20mae = np.minimum(_project_with_q(_by_age(t, 26, 20, 115), q, lt_last,
                                                 20, 115, True, q), 1.)
    t = read_rate_file(p("shk_izoku"))
    if sex == MALE:
        tuma = _by_age(t, 27, 20, 115)
        tuma[AGES.i(18)] = tuma[AGES.i(19)] = tuma[AGES.i(20)]
        R.shikken_tuma = _all_years(tuma)
        R.shikken_ko = _all_years(_by_age(t, 28, 0, 19))
        R.shikken_kafu = _all_years(_by_age(t, 29, 26, 64))
        R.shikken_otto = zero.copy()
    else:
        R.shikken_tuma = zero.copy()
        R.shikken_ko = zero.copy()
        R.shikken_kafu = zero.copy()
        R.shikken_otto = None            # 妻の失権率が要るので後で `blend_otto()`
        R._otto0 = _by_age(t, 27, 18, 115)

    # ---- 支給率 ----
    t = read_rate_file(p("shikyu"))
    R.shikyuritu_rorei = _rorei_shikyu(t, 301)
    R.shikyuritu_rorei_kyu = _kyu_shikyu(t, 302)
    R.shikyuritu_turo_kyu = _kyu_shikyu(t, 303)
    R.shikyuritu_gonen = _gonen_shikyu(t)
    y_first = pol.get("kokunen.years.suikei_shonendo")
    R.shikyuritu_shogai_ippan = _shogai_shikyu(t, 305, sex, y_first)
    R.shikyuritu_shogai_20mae = _shogai_shikyu(t, 306, sex, y_first)
    R.shikyuritu_shogai_kyu = _shogai_kyu_shikyu(t)
    v308 = t[308][308]
    if sex == MALE:
        R.shikyuritu_tuma = np.full(YEARS.n, v308[0])
        R.shikyuritu_ko = np.full(YEARS.n, v308[1])
        R.shikyuritu_otto = np.zeros(YEARS.n)
        kf = np.zeros(AGES.n)
        for age in range(60, 64 + 1):
            kf[AGES.i(age)] = t[309][age][0]
        R.shikyuritu_kafu = _all_years(kf)
    else:
        R.shikyuritu_otto = np.full(YEARS.n, v308[0])
        R.shikyuritu_tuma = np.zeros(YEARS.n)
        R.shikyuritu_ko = np.zeros(YEARS.n)
        R.shikyuritu_kafu = np.zeros((YEARS.n, AGES.n))

    # ---- 一部繰上げの拡大・割引率・給付率 ----
    R.kakudai_ichibu = _read_ichibu(p("ichibu"))
    R.waribiki_n, R.waribiki_b = _read_waribiki(os.path.join(kisoritu_dir, "waribiki_2024.csv"),
                                                *pol.get("kokunen.waribiki_years"))
    R.kyufu_ritu = _read_kyufu(os.path.join(kisoritu_dir, "kyufu_2024_1.csv"),
                               os.path.join(kisoritu_dir, "kyufu_2024_2.csv"),
                               pol.get("kokunen.years.henkou_seinendo"),
                               pol.get("kokunen.kyufu2_cohort"))
    return R


def _first_value(path, tag):
    """`(tag, 値)` の1行の値。"""
    for l in lines_of(path):
        f = [x.strip() for x in l.split(",")]
        try:
            vals = [float(x) for x in f if x != ""]
        except ValueError:
            continue
        if len(vals) >= 2 and int(vals[0]) == tag:
            return vals[1]
    raise ValueError("%s: %d が無い" % (path, tag))


def blend_otto(female, male):
    """夫の失権率: 13年かけて2歳若い妻の失権率へ線形に寄せる。港: nat/kiso.py:kiso（876〜895行）"""
    o0 = female._otto0
    tuma0 = male.shikken_tuma[YEARS.i(2020)]
    out = np.zeros((YEARS.n, AGES.n))
    n = 13
    for k in range(1, n + 1):
        yi = YEARS.i(2020 + k)
        for age in range(18, 115 + 1):
            ai = AGES.i(age)
            out[yi, ai] = ((n - k) * o0[ai] + k * tuma0[AGES.i(age - 2)]) / float(n)
    out[YEARS.i(2020 + n) + 1:] = out[YEARS.i(2020 + n)]
    female.shikken_otto = out
    return female
