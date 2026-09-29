# -*- coding: utf-8 -*-
"""③国民年金の年度ループと集計（移植版 `main.c` `shke.c` `stat.c` 相当）
========================================================================
区分（第1号男・第3号男・第1号女・第3号女）ごとに

    2021年度末の状態（`initial.read_initial`）
    → 2022〜2125年度: 納付状況 → 遷移（`transition_year`）→ 新規発生（`shinki_*`）
                        → 年度末（`yearend_*`）→ 年度中の集計（`aggregate_year`）

を回し、最後に男女・全体の計と年度間の量を作って `NatOut` にする（`finalize`）。
区分の計は**計算で出す**（港の `SHUBETU_SUM`・`SHUBETU_OTOKO/ONNA` のような
魔法の添字は持たない）。

年度中の集計（港: shke.c）
    受給[y, m, …] = Σ_{x ∈ 階級 m} 支給率[y, x] · 年度末[y, x, …]
    被保険者[y, x] = Σ_t 被保険者[y, x, t]、納付[y, x] = 被保険者[y, x] · 納付率[y, x]、
    `_P`（翌年度の率で見たぶん） = 被保険者[y, x] · 納付率[y+1, x+1]

年度間の量（港: stat.c）
    被保険者・納付・免除・付加の年度計 = (前年度の `_P` ＋ 当年度) / 2   （2022年度以降）
    年度間受給者数[0] = 63歳以下〜115歳の計、[1] = 63・64歳だけ
    死亡一時金の2021年度は足元が無いので 2022年度の値で埋める（港のまま）

港: nat/main.py:main, PerformSiml
港: nat/shke.py:shke
港: nat/stat.py:stat, Hanbetu
仕様: §4.2、§5.1〜5.3、§12.4
"""
from dataclasses import dataclass, field
import os

import numpy as np

from ...axis import YEARS, AGES, COHORTS
from ...contracts import NatOut, Provenance, policy_hash, git_rev
from ...econ import read_econ_csv, kaiteiritu
from .aggregate import AGE_CLASS_N, sum_by_class, apply_waribiki, menjo_totals
from .benefits import (NatState, Shinki, KURIAGE_N, ROREI_MIN, ROREI_MAX, TOKYU_N,
                       SHOGAI_MIN, SHOGAI_MAX, TUMA_MIN, OTTO_MIN, KO_MIN, KO_MAX, IZOKU_MAX,
                       KAFU_MIN, KAFU_MAX, shinki_shogai, shinki_izoku, shinki_kafu,
                       shinki_ichijikin, shinki_rorei, yearend_rorei, yearend_shogai,
                       yearend_izoku, yearend_kafu)
from .initial import read_initial
from .inputs import MALE, FEMALE, read_sotowaku, read_lifetable, read_yuhaigu
from .layouts import (ROREI, ROREI_KYU, GONEN, SHOGAI, IZOKU, KAFU, ICHIJIKIN,
                      MENJO_DANKAI)
from . import noufuritu as NF
from .rates import read_rates, blend_otto
from .transition import (transition_year, noufu_jokyo, kokko_frac, AGE_MIN as HIHO_MIN,
                         AGE_MAX as HIHO_MAX)

__all__ = ["NatClass", "CLASSES", "NatInputs", "read_inputs", "Series", "run",
           "aggregate_year", "finalize", "NatRun", "shibou_kubun"]

_SEX_ID = {"male": MALE, "female": FEMALE}


@dataclass(frozen=True)
class NatClass:
    """被保険者の区分（港の種別 2・3・5・6）。"""
    name: str        # "1m" "3m" "1f" "3f"
    sex: str         # "male" | "female"
    gou: int         # 1 | 3
    port_shubetu: int

    @property
    def sex_id(self):
        return _SEX_ID[self.sex]


CLASSES = (NatClass("1m", "male", 1, 2), NatClass("3m", "male", 3, 3),
           NatClass("1f", "female", 1, 5), NatClass("3f", "female", 3, 6))
_HIHO_A = slice(AGES.i(HIHO_MIN), AGES.i(HIHO_MAX) + 1)
_HIHO_AGES = np.arange(HIHO_MIN, HIHO_MAX + 1)


def shibou_kubun(noufu_kikan):
    """死亡一時金の単価の区分（納付年数 15/20/25/30/35/40 で 0〜5）。港: nat/siml.py:Shibou_Kubun"""
    edges = np.array([15., 20., 25., 30., 35., 40.])
    return np.searchsorted(edges, np.asarray(noufu_kikan), side="right")


def kanou_nensu_table(pol):
    """加入可能年数 (YEARS.n, COHORTS.n)。港: nat/seid.py:seid"""
    pts = {int(k): v for k, v in pol.get("kokunen.kanou_nensu.points").items()}
    c0 = min(pts)
    v0, vmax = pts[c0], max(pts.values())
    c = COHORTS.labels()
    row = np.minimum(v0 + (c - c0), vmax).astype(np.float64)
    return np.repeat(row[None, :], YEARS.n, axis=0)


@dataclass
class NatInputs:
    pol: object
    econ: object                 # KaiteiResult
    sotowaku: object
    lifetable: object
    yuhaigu: dict
    noufu: object                # NoufuResult
    rates: dict                  # name → Rates
    initial: dict                # name → NatState（2021年度末）
    kanou_nensu: np.ndarray      # (YEARS.n, COHORTS.n)
    hokenryou_wariai: np.ndarray  # (5,)
    kokko_wariai: np.ndarray     # (3,)
    shogai_bairitu: np.ndarray   # (3,)
    tanka_shibou: np.ndarray     # (YEARS.n, 7)
    tanka_fuka: float
    fuka_tanka: float            # 付加年金の単価（年あたり）


def read_inputs(pol, nat_dir, waku_dir, case, econ_csv, lifetable="QX-M2023.csv",
                birth="birth_ratio_0.csv", first_year=None):
    """③の入力を全部読む。`nat_dir` は `work/suuri/rev2024/nat`。"""
    kis = os.path.join(nat_dir, "base_data", "kisoritu")
    kisosu = os.path.join(nat_dir, "base_data", "kisosu")
    econ = kaiteiritu(pol, read_econ_csv(econ_csv))
    sw = read_sotowaku(waku_dir, case)
    lt = read_lifetable(os.path.join(kis, lifetable))
    yh = read_yuhaigu(os.path.join(kis, "yu_haigu_2024.csv"))
    nf = NF.noufuritu(pol, NF.read_noufu_inputs(kis, os.path.join(kis, birth)), sw)
    rates, initial = {}, {}
    for sex in ("male", "female"):
        sid = _SEX_ID[sex]
        r1 = read_rates(pol, kis, sid, 1, lt, yh)
        rates["1" + sex[0]] = r1
    blend_otto(rates["1f"], rates["1m"])
    for sex in ("male", "female"):
        sid = _SEX_ID[sex]
        rates["3" + sex[0]] = read_rates(pol, kis, sid, 3, lt, yh, base=rates["1" + sex[0]])
    for cls in CLASSES:
        initial[cls.name] = read_initial(kisosu, cls.sex, cls.gou)
    hw = np.array([0., 0., pol.get("kokunen.hokenryou_wariai.menjo_3_4"),
                   pol.get("kokunen.hokenryou_wariai.menjo_1_2"),
                   pol.get("kokunen.hokenryou_wariai.menjo_1_4")])
    kw = np.array([0., pol.get("kokunen.kokko_wariai.before"), pol.get("kokunen.kokko_wariai.after")])
    sb = np.array([0., pol.get("kokunen.shogai_bairitu.kyu1"), pol.get("kokunen.shogai_bairitu.kyu2")])
    ts = list(pol.get("kokunen.amounts_2004.shibou_ichijikin"))
    ts.append(ts[-1])                                     # 区分 6（45年化なしでは 5 と同じ）
    tanka = np.repeat(np.array(ts, dtype=np.float64)[None, :], YEARS.n, axis=0)
    return NatInputs(pol, econ, sw, lt, yh, nf, rates, initial, kanou_nensu_table(pol),
                     hw, kw, sb, tanka, float(pol.get("kokunen.amounts_2004.shibou_fuka")),
                     float(pol.get("kokunen.amounts_2004.fuka")))


# ---------------------------------------------------------------- 集計

@dataclass
class Series:
    """1つの区分の年度ごとの集計（港の `Hiho_*`・`Rorei` 等の1種別ぶん）。"""
    hiho_kei: np.ndarray = field(default_factory=lambda: YEARS.zeros(AGES.n))
    hiho_noufu: np.ndarray = field(default_factory=lambda: YEARS.zeros(AGES.n))
    fuka_hiho: np.ndarray = field(default_factory=lambda: YEARS.zeros(AGES.n))
    hiho_menjo: np.ndarray = field(default_factory=lambda: YEARS.zeros(AGES.n, MENJO_DANKAI))
    hiho_noufu_p: np.ndarray = field(default_factory=lambda: YEARS.zeros(AGES.n))
    fuka_hiho_p: np.ndarray = field(default_factory=lambda: YEARS.zeros(AGES.n))
    hiho_menjo_p: np.ndarray = field(default_factory=lambda: YEARS.zeros(AGES.n, MENJO_DANKAI))
    rorei: np.ndarray = field(default_factory=lambda: YEARS.zeros(AGE_CLASS_N, KURIAGE_N, ROREI.n))
    rorei_kyu: np.ndarray = field(default_factory=lambda: YEARS.zeros(AGE_CLASS_N, KURIAGE_N, ROREI_KYU.n))
    turo_kyu: np.ndarray = field(default_factory=lambda: YEARS.zeros(AGE_CLASS_N, KURIAGE_N, ROREI_KYU.n))
    gonen: np.ndarray = field(default_factory=lambda: YEARS.zeros(AGE_CLASS_N, KURIAGE_N, GONEN.n))
    shogai_ippan: np.ndarray = field(default_factory=lambda: YEARS.zeros(AGE_CLASS_N, SHOGAI.n))
    shogai_20mae: np.ndarray = field(default_factory=lambda: YEARS.zeros(AGE_CLASS_N, SHOGAI.n))
    shogai_kyu: np.ndarray = field(default_factory=lambda: YEARS.zeros(AGE_CLASS_N, SHOGAI.n))
    izoku_tuma: np.ndarray = field(default_factory=lambda: YEARS.zeros(AGE_CLASS_N, IZOKU.n))
    izoku_otto: np.ndarray = field(default_factory=lambda: YEARS.zeros(AGE_CLASS_N, IZOKU.n))
    izoku_ko: np.ndarray = field(default_factory=lambda: YEARS.zeros(IZOKU.n))
    kafu: np.ndarray = field(default_factory=lambda: YEARS.zeros(KAFU.n))
    kafu_kyu: np.ndarray = field(default_factory=lambda: YEARS.zeros(KAFU.n))
    ichijikin: np.ndarray = field(default_factory=lambda: YEARS.zeros(AGE_CLASS_N, ICHIJIKIN.n))
    # 年度末の人数（検証用。港の `*_Nendomatu` の人数の年齢計）
    nendomatu_rorei: np.ndarray = field(default_factory=lambda: YEARS.zeros())
    nendomatu_hiho: np.ndarray = field(default_factory=lambda: YEARS.zeros())
    nendomatu_taiki: np.ndarray = field(default_factory=lambda: YEARS.zeros())


def _noufu_rows(inp, cls, yi):
    """区分・年度の納付率 (AGES.n, 11) と付加の納付率 (AGES.n,)。第3号は付加なし。"""
    if cls.gou == 1:
        return inp.noufu.noufuritu[cls.sex_id][yi], inp.noufu.noufuritu_fuka[cls.sex_id][yi]
    return inp.noufu.noufuritu_3gou[yi], np.zeros(AGES.n)


def _menjo_rates(nr):
    """納付率の行 (AGES.n, 11) → 免除段階 1〜4 の割合 (AGES.n, 5)。全額 = 法定 ＋ 申請。"""
    out = np.zeros((AGES.n, MENJO_DANKAI))
    out[:, 1] = nr[:, NF.MENJO_HOUTEI] + nr[:, NF.MENJO_SHINSEI]
    out[:, 2] = nr[:, NF.MENJO_3_4]
    out[:, 3] = nr[:, NF.MENJO_1_2]
    out[:, 4] = nr[:, NF.MENJO_1_4]
    return out


def aggregate_year(inp, cls, state, yi, S):
    """年度 `yi` の年度末の状態 `state` を年度中の量にして `S`（Series）に書く。港: nat/shke.py:shke"""
    year = YEARS.label(yi)
    R = inp.rates[cls.name]
    # ---- 被保険者 ----
    kei = state.hiho.H[:, :, 0].sum(axis=1)                       # (AGES.n,)
    nr, fk = _noufu_rows(inp, cls, yi)
    S.hiho_kei[yi] = kei
    S.hiho_noufu[yi] = kei * nr[:, NF.NOUFU]
    S.fuka_hiho[yi] = kei * fk
    S.hiho_menjo[yi] = kei[:, None] * _menjo_rates(nr)
    yn = min(yi + 1, YEARS.n - 1)                                 # 最終年度は年度を進めない
    nr_n, fk_n = _noufu_rows(inp, cls, yn)
    nxt = np.zeros(AGES.n)                                        # 翌年度・1歳上の率
    nxt[:-1] = nr_n[1:, NF.NOUFU]
    fkn = np.zeros(AGES.n)
    fkn[:-1] = fk_n[1:]
    mjn = np.zeros((AGES.n, MENJO_DANKAI))
    mjn[:-1] = _menjo_rates(nr_n)[1:]
    for a in (nxt, fkn, mjn):
        a[AGES.i(HIHO_MAX)] = 0.                                  # 70歳は 0（港のまま）
    S.hiho_noufu_p[yi] = kei * nxt
    S.fuka_hiho_p[yi] = kei * fkn
    S.hiho_menjo_p[yi] = kei[:, None] * mjn
    S.nendomatu_hiho[yi] = kei.sum()
    S.nendomatu_taiki[yi] = state.hiho.T[:, :, 0].sum()

    # ---- 老齢（新法＋一部繰上げ・旧法・通算・5年） ----
    ages = np.arange(ROREI_MIN, ROREI_MAX + 1)
    sl = AGES.s(ROREI_MIN, ROREI_MAX)
    sh = R.shikyuritu_rorei[yi][:, None, :] * (state.rorei + state.rorei_ichibu)
    w_first, w_last = inp.pol.get("kokunen.waribiki_years")
    apply_waribiki(sh, year, range(66, 70 + 1),
                   lambda age: AGES.i(age) if ROREI_MIN <= age <= ROREI_MAX else None,
                   R.waribiki_n, R.waribiki_b, w_first, w_last,
                   ninzu_after_k=1 if inp.pol.get("kokunen.quirks.j3_waribiki_ninzu_2023") else None)
    S.rorei[yi] = menjo_totals(sum_by_class(sh[sl], ages), ROREI)
    S.rorei_kyu[yi] = sum_by_class((R.shikyuritu_rorei_kyu[yi][:, None, :] * state.rorei_kyu)[sl], ages)
    S.turo_kyu[yi] = sum_by_class((R.shikyuritu_turo_kyu[yi][:, None, :] * state.turo_kyu)[sl], ages)
    S.gonen[yi] = sum_by_class((R.shikyuritu_gonen[yi][:, None, None] * state.gonen)[sl], ages)
    S.nendomatu_rorei[yi] = (state.rorei + state.rorei_ichibu)[sl, :, 0].sum()

    # ---- 障害 ----
    ages = np.arange(SHOGAI_MIN, SHOGAI_MAX + 1)
    sl = AGES.s(SHOGAI_MIN, SHOGAI_MAX)
    for name, rate in (("shogai_ippan", R.shikyuritu_shogai_ippan),
                       ("shogai_20mae", R.shikyuritu_shogai_20mae),
                       ("shogai_kyu", R.shikyuritu_shogai_kyu)):
        v = (rate[yi][:, :, None] * getattr(state, name))[sl].sum(axis=1)   # 等級を潰す
        getattr(S, name)[yi] = sum_by_class(v, ages)

    # ---- 遺族 ----
    sl = AGES.s(TUMA_MIN, IZOKU_MAX)
    S.izoku_tuma[yi] = sum_by_class((R.shikyuritu_tuma[yi] * state.izoku_tuma)[sl],
                                    np.arange(TUMA_MIN, IZOKU_MAX + 1))
    sl = AGES.s(OTTO_MIN, IZOKU_MAX)
    S.izoku_otto[yi] = sum_by_class((R.shikyuritu_otto[yi] * state.izoku_otto)[sl],
                                    np.arange(OTTO_MIN, IZOKU_MAX + 1))
    S.izoku_ko[yi] = (R.shikyuritu_ko[yi] * state.izoku_ko)[AGES.s(KO_MIN, KO_MAX)].sum(axis=0)

    # ---- 寡婦（60〜64歳だけ） ----
    sl = AGES.s(60, KAFU_MAX)
    S.kafu[yi] = menjo_totals((R.shikyuritu_kafu[yi][:, None] * state.kafu)[sl].sum(axis=0), KAFU)
    S.kafu_kyu[yi] = menjo_totals((R.shikyuritu_kafu[yi][:, None] * state.kafu_kyu)[sl].sum(axis=0), KAFU)

    # ---- 死亡一時金（支給率を掛けない） ----
    S.ichijikin[yi] = sum_by_class(state.ichijikin[_HIHO_A], _HIHO_AGES)


# ---------------------------------------------------------------- 年度ループ

def izoku_lifetable(inp, cls):
    """遺族の 60〜64歳の枝で引く生命表 `q[YEARS.i(y), AGES.i(x)]`。

    既定（`kokunen.quirks.b11_izoku_lifetable_sex` = true）は原本どおり（台帳 B11）: 性別の添字が
    1 つずれて、男は**女**の表の同じ年齢、女は配列の外 = **男**の表の 1 歳上を読む。false なら自分の性別。
    港: nat/siml.py:siml（`_izoku` の `_c_at(G.q, yq, nenrei, seibetu)`）"""
    q = inp.lifetable.q
    if not inp.pol.get("kokunen.quirks.b11_izoku_lifetable_sex"):
        return q[cls.sex_id]
    if cls.sex == "male":
        return q[FEMALE]
    out = np.zeros_like(q[MALE])
    out[:, :-1] = q[MALE][:, 1:]
    return out


def step_year(inp, cls, prev, yi):
    """区分 `cls` を年度 `yi` に1年進める。戻り値は当年度末の `NatState`。港: nat/siml.py:siml"""
    year = YEARS.label(yi)
    pol, R, E = inp.pol, inp.rates[cls.name], inp.econ
    sw = inp.sotowaku
    pop, gou2 = sw.jinko[cls.sex_id], sw.gou2[cls.sex_id]
    waku = (sw.gou1 if cls.gou == 1 else sw.gou3)[cls.sex_id][yi]
    nr, fk = _noufu_rows(inp, cls, yi)
    nj = noufu_jokyo(nr, fk)

    hiho, flows = transition_year(prev.hiho, waku, R.dattai_gokei[yi], R.dattai_shibou[yi],
                                  R.shikken_rorei[yi], R.saikanyuritu[yi],
                                  R.hasseiryoku_shogai[yi], nj, kokko_frac(pol, year))
    mangaku = E.mangaku
    ippan, mae = shinki_shogai(R, yi, cls, flows, pop, gou2, mangaku, inp.shogai_bairitu)
    tuma, otto, ko = shinki_izoku(R, yi, cls, flows, pop, gou2, izoku_lifetable(inp, cls),
                                  mangaku)
    kafu = shinki_kafu(R, yi, cls, flows, mangaku, inp.kanou_nensu, inp.hokenryou_wariai,
                       inp.kokko_wariai)
    ichiji = shinki_ichijikin(R, yi, cls, flows, nj, inp.hokenryou_wariai, inp.tanka_shibou[yi],
                              inp.tanka_fuka, shibou_kubun)
    kr = R.kyufu_ritu
    rorei = shinki_rorei(R, yi, cls, hiho, mangaku, inp.kanou_nensu,
                         lambda j, cohort, sex: kr[(ROREI_MIN + j, cohort)],
                         inp.fuka_tanka, inp.hokenryou_wariai, inp.kokko_wariai)
    shinki = Shinki(rorei, ippan, mae, tuma, otto, ko, kafu)

    kt = E.tannen[yi]
    lo, hi = pol.get("kokunen.kakudai_ichibu.cohorts")
    cohort65 = year - 65
    kakudai = R.kakudai_ichibu.get(cohort65) if lo <= cohort65 <= hi else None
    cur = NatState(hiho=hiho)
    for k, v in yearend_rorei(prev, shinki, yi, R, kt, kakudai).items():
        setattr(cur, k, v)
    k12, k3 = E.kakyu_12shi[yi], E.kakyu_3shiiko[yi]
    cur.shogai_ippan, cur.shogai_20mae, cur.shogai_kyu = yearend_shogai(
        prev, ippan, mae, yi, R, kt, k12, k3)
    cur.izoku_tuma, cur.izoku_otto, cur.izoku_ko = yearend_izoku(
        prev, tuma, otto, ko, yi, R, kt, k12, k3)
    cur.kafu, cur.kafu_kyu = yearend_kafu(prev, kafu, yi, R,
                                          kt[AGES.i(pol.get("kokunen.ages.under_67"))])
    cur.ichijikin = ichiji
    return cur


@dataclass
class NatRun:
    out: NatOut
    series: dict            # name → Series
    states: dict            # name → 最終年度末の NatState


def run(inp, case, last_year=None, keep_states=False):
    """③を通しで回す。`last_year` で年数を縮められる（テスト用）。港: nat/main.py:main"""
    pol = inp.pol
    y0 = pol.get("kokunen.years.suikei_shonendo")
    last = YEARS.last if last_year is None else last_year
    series, states = {}, {}
    for cls in CLASSES:
        S = Series()
        st = inp.initial[cls.name]
        aggregate_year(inp, cls, st, YEARS.i(y0), S)
        for year in range(y0 + 1, last + 1):
            st = step_year(inp, cls, st, YEARS.i(year))
            aggregate_year(inp, cls, st, YEARS.i(year), S)
        series[cls.name] = S
        states[cls.name] = st
    out = finalize(inp, series, case)
    return NatRun(out, series, states)


# ---------------------------------------------------------------- 計と出力の系列

def _sum(series, names, attr):
    return sum(getattr(series[n], attr) for n in names)


def finalize(inp, series, case):
    """男女・全体の計、年度間の量、④への受け渡し（KISONENKIN）と独自給付（DOKUZI）。
    港: nat/stat.py:stat"""
    pol = inp.pol
    y0 = pol.get("kokunen.years.suikei_shonendo")
    yi0 = YEARS.i(y0)
    by_sex = {"male": ("1m", "3m"), "female": ("1f", "3f")}

    # ---- 被保険者の年度間の計（年齢計だけ。2022年度以降は前年度の _P と平均） ----
    hiho = {}
    for name, S in series.items():
        kei = S.hiho_kei.sum(axis=1)
        noufu = S.hiho_noufu.sum(axis=1)
        fuka = S.fuka_hiho.sum(axis=1)
        menjo = S.hiho_menjo.sum(axis=1)
        avg = {"kei": kei.copy(), "noufu": noufu.copy(), "fuka": fuka.copy(), "menjo": menjo.copy()}
        s = slice(yi0 + 1, YEARS.n)
        avg["kei"][s] = (kei[yi0:-1] + kei[s]) / 2.
        avg["noufu"][s] = (S.hiho_noufu_p.sum(axis=1)[yi0:-1] + noufu[s]) / 2.
        avg["fuka"][s] = (S.fuka_hiho_p.sum(axis=1)[yi0:-1] + fuka[s]) / 2.
        avg["menjo"][s] = (S.hiho_menjo_p.sum(axis=1)[yi0:-1] + menjo[s]) / 2.
        hiho[name] = avg

    # ---- 性別の計（受給年齢も潰す） ----
    sx = {}
    for sex, names in by_sex.items():
        d = {}
        for attr in ("rorei", "rorei_kyu", "turo_kyu", "gonen"):
            d[attr] = _sum(series, names, attr).sum(axis=2)          # (YEARS, m, slots)
            d[attr + "_ninzu"] = _sum(series, names, attr)[..., 0]  # (YEARS, m, j)
        for attr in ("shogai_ippan", "shogai_20mae", "shogai_kyu", "izoku_tuma", "izoku_otto",
                     "izoku_ko"):
            d[attr] = _sum(series, names, attr)
        sx[sex] = d
    allc = tuple(series)
    tot = {}
    for attr in ("rorei", "rorei_kyu", "turo_kyu", "gonen"):
        tot[attr] = _sum(series, allc, attr)[:, 1:].sum(axis=(1, 2))   # (YEARS, slots)
    tot["shogai_kyu"] = _sum(series, allc, "shogai_kyu")[:, 1:].sum(axis=1)
    for attr in ("kafu", "kafu_kyu"):
        tot[attr] = _sum(series, allc, attr)
    ic = _sum(series, allc, "ichijikin")[:, 1:].sum(axis=1)
    ic[yi0] = ic[yi0 + 1]                                            # 足元の埋め合わせ（港のまま）
    tot["ichijikin"] = ic

    # ---- KISONENKIN の表（年度 × 階級 m=1..53 × 性） ----
    n_m = AGE_CLASS_N
    K = {}
    K["1-1"] = np.zeros((YEARS.n, n_m, 2, 4))
    K["1-2"] = np.zeros((YEARS.n, n_m, 2, 5))
    K["1-3"] = np.zeros((YEARS.n, n_m, 2, 2))
    K["2-1"] = np.zeros((YEARS.n, n_m, 2, 6))
    K["2-2"] = np.zeros((YEARS.n, n_m, 2, 4))
    K["2-3"] = np.zeros((YEARS.n, n_m, 2, 4))
    i_r = {k: ROREI.i(k) for k in ("noufu", "menjo[0][1]", "menjo[0][2]", "rofuku_shitasasae", "fuka")}
    i_k = {k: ROREI_KYU.i(k) for k in ("noufu", "menjo", "kasa_noufu", "kasa_menjo",
                                       "rofuku_shitasasae", "fuka")}
    i_s = {k: SHOGAI.i(k) for k in ("kihon", "kakyu", "menjo_kihon", "menjo_kakyu")}
    i_i = {k: IZOKU.i(k) for k in ("ninzu", "kihon", "kakyu")}
    for si, sex in enumerate(("male", "female")):
        d = sx[sex]
        r = d["rorei"]
        K["1-1"][:, :, si, 0] = r[..., i_r["noufu"]]
        K["1-1"][:, :, si, 1] = r[..., i_r["menjo[0][1]"]] + r[..., i_r["rofuku_shitasasae"]]
        K["1-1"][:, :, si, 2] = r[..., i_r["menjo[0][2]"]]
        ip, mn = d["shogai_ippan"], d["shogai_20mae"]
        K["1-2"][:, :, si, 0] = ip[..., i_s["kihon"]]
        K["1-2"][:, :, si, 1] = ip[..., i_s["kakyu"]]
        K["1-2"][:, :, si, 3] = mn[..., i_s["kihon"]]
        K["1-2"][:, :, si, 4] = mn[..., i_s["kakyu"]]
        tu, ot, ko = d["izoku_tuma"], d["izoku_otto"], d["izoku_ko"]
        for c, f in ((0, "kihon"), (1, "kakyu")):
            v = tu[..., i_i[f]] + ot[..., i_i[f]]
            v[:, 1] += ko[:, i_i[f]]                                  # 子は 63歳以下の行に
            K["1-3"][:, :, si, c] = v
        rk, tk, gn = d["rorei_kyu"], d["turo_kyu"], d["gonen"]
        for c, f in enumerate(("noufu", "menjo", "kasa_noufu", "kasa_menjo", "rofuku_shitasasae")):
            K["2-1"][:, :, si, c] = rk[..., i_k[f]] + tk[..., i_k[f]]
        K["2-1"][:, :, si, 5] = gn[..., GONEN.i("noufu")]
        sk = d["shogai_kyu"]
        K["2-2"][:, :, si, 0] = sk[..., i_s["kihon"]] - sk[..., i_s["menjo_kihon"]]
        K["2-2"][:, :, si, 1] = sk[..., i_s["menjo_kihon"]]
        K["2-2"][:, :, si, 2] = sk[..., i_s["kakyu"]] - sk[..., i_s["menjo_kakyu"]]
        K["2-2"][:, :, si, 3] = sk[..., i_s["menjo_kakyu"]]
    K["1-1"][:yi0] = 0.                                               # 足元より前は無い

    # 保険料の納付月数（第1号男・女）＋ 産前産後・育児期間
    beta = inp.hokenryou_wariai
    nm = np.zeros((YEARS.n, 4))
    for c, name in enumerate(("1m", "1f")):
        h = hiho[name]
        nm[:, c] = h["noufu"] + (h["menjo"][:, 1:] * beta[None, 1:]).sum(axis=1)
    nm[:, 2] = inp.noufu.sankyu_sum
    nm[:, 3] = inp.noufu.ikukyu_sum
    K["noufu_months"] = nm

    # 年度間受給者数（性 × [63歳以下〜115歳, 63・64歳]）
    def two(v):                                                       # v: (YEARS, m[, j])
        v = v.reshape(v.shape[0], v.shape[1], -1).sum(axis=2)
        return np.stack([v[:, 1:].sum(axis=1), v[:, 1:3].sum(axis=1)], axis=1)
    nr = np.zeros((YEARS.n, 2, 9))
    ns = np.zeros((YEARS.n, 2, 4))
    ni = np.zeros((YEARS.n, 2, 2))
    ko_all = np.zeros(YEARS.n)
    for si, sex in enumerate(("male", "female")):
        d = sx[sex]
        nr[:, si, 0:2] = two(d["rorei_ninzu"])
        nr[:, si, 4:6] = two(d["rorei_kyu_ninzu"])
        nr[:, si, 6:8] = two(d["turo_kyu_ninzu"])
        nr[:, si, 8] = two(d["gonen_ninzu"])[:, 0]
        ip = two(d["shogai_ippan"][..., 0]) + two(d["shogai_20mae"][..., 0])
        ns[:, si, 0:2] = ip
        ns[:, si, 2:4] = two(d["shogai_kyu"][..., 0])
        ni[:, si] = two(d["izoku_tuma"][..., 0]) + two(d["izoku_otto"][..., 0])
        ko_all += d["izoku_ko"][:, 0]
    K["nendokan_rorei"], K["nendokan_shogai"] = nr, ns
    K["nendokan_izoku_ko"] = ko_all
    K["nendokan_izoku"] = ni.sum(axis=1) + ko_all[:, None]

    # ---- DOKUZI（独自給付） ----
    r, rk, tk, sk = tot["rorei"], tot["rorei_kyu"], tot["turo_kyu"], tot["shogai_kyu"]
    kf, kk, ic = tot["kafu"], tot["kafu_kyu"], tot["ichijikin"]
    D = np.zeros((YEARS.n, 10))
    D[:, 0] = hiho["1m"]["fuka"] + hiho["1f"]["fuka"]
    D[:, 1] = r[:, i_r["fuka"]]
    D[:, 2] = rk[:, i_k["fuka"]]
    D[:, 3] = tk[:, i_k["fuka"]]
    D[:, 4] = kf[:, KAFU.i("noufu")] + kf[:, KAFU.i("menjo[0][0]")]
    D[:, 5] = kk[:, KAFU.i("noufu")]
    D[:, 6] = kk[:, KAFU.i("menjo[0][0]")]
    D[:, 7] = ic[:, ICHIJIKIN.i("kyufu")]
    D[:, 8] = ic[:, ICHIJIKIN.i("kyufu_fuka")]
    D[:, 9] = (r[:, ROREI.i("menjo[0][0]")] + rk[:, i_k["menjo"]] + rk[:, i_k["kasa_menjo"]]
               + tk[:, i_k["menjo"]] + tk[:, i_k["kasa_menjo"]]
               + sk[:, i_s["menjo_kihon"]] + sk[:, i_s["menjo_kakyu"]])

    prov = Provenance(case=case, stage="s3", source="fast", policy=policy_hash(pol.data),
                      rev=git_rev())
    return NatOut(prov=prov, kisonenkin=K, dokuzi={"table": D, "hiho": hiho},
                  kokukaite=inp.econ.tannen.copy())
