# -*- coding: utf-8 -*-
"""②の制度定数・支給率・報酬水準（移植版 `seid.cpp`）
=====================================================
1. 法定の定数（生年度別テーブルは yaml `kounen.*` から）→ `Seid`
2. 支給率 `sik` を基準年度の翌年度の値から将来へ伸ばす → `sik_extend`
3. 報酬水準 `bn` `br` と男女差の縮小、パートの平均報酬 → `set_hsr`

生年度別のテーブル（`flt` `sadt` `cadt` `wife` `can` `can2` `pre` `pres`）は
`ALL_COHORTS`（年度 − 年齢の全域）の軸で持ち、`cohort_idx(年度, 年齢)` で引く。
移植版の `C19(kx)` の代わり。

J1（定額部分の生年別読替率の 1936 年度生が `369`）は既定では**原本どおり**。`fix_bugs` で
1.369 に直る（yaml `kounen.tables.tmq`。`検証/原本の不具合.md` J1。2022 年度以降の出力には現れない）。

港: emp_kyufu/seid.py:seid, set_hsr
仕様: §5.4〜5.5（給付乗率・定額単価・加給）、§4.3（報酬水準）
"""
from dataclasses import dataclass

import numpy as np

from ...axis import YEARS, ALL_COHORTS
from .econ import c_round, roundn
from .inputs import NX

_EPS_PART = 1.0e-6

__all__ = ["Seid", "seid_consts", "sik_extend", "Hoshu", "set_hsr", "cohort_idx", "kflcan_table"]


def cohort_idx(year_idx, age):
    """(年度の添字, 年齢) → `ALL_COHORTS` の添字。どちらも配列でよい。"""
    return YEARS.label(np.asarray(year_idx)) - np.asarray(age) - ALL_COHORTS.first


def _by_cohort(points, default=0.):
    """{生年度: 値} の階段を `ALL_COHORTS` の配列に。最初の点より前は `default`。"""
    c = ALL_COHORTS.labels()
    out = np.full(ALL_COHORTS.n, float(default))
    for key, val in sorted((int(k), v) for k, v in points.items()):
        out[c >= key] = float(val)
    return out


@dataclass
class Seid:
    pre: np.ndarray           # 報酬比例の乗率（本来水準）[cohort]
    pres: np.ndarray          # 同（従前額保障）
    flt: np.ndarray           # 定額部分の生年別読替率
    fl1: float                # 定額部分の単価（年額、基準年度価格）
    fl: float                 # 同（月額単価 × 12。1円に丸め）
    minb: float               # 報酬比例の最低保障
    adt: np.ndarray           # 加給年金額 [1 配偶者, 2 第1・2子, 3 第3子以降]
    sadt: np.ndarray          # 配偶者加給の特別加算 [cohort]
    cadt: np.ndarray          # 中高齢寡婦加算 [cohort]
    wif: float
    wife: np.ndarray          # 経過的寡婦加算 [cohort]
    can: np.ndarray           # 加入可能年数 [cohort]
    can2: np.ndarray
    senll: float              # 長期加入者の特例（年）
    ha: np.ndarray            # 障害の等級別乗率 [1..3]
    hb: np.ndarray
    ema: np.ndarray           # 障害の加算率
    emb: np.ndarray
    emc: np.ndarray
    srv: float                # 遺族の給付割合
    ee: np.ndarray            # [1] 脱退一時金の率（制度で違う）, [2] 0.25


def kflcan_table(pol):
    """基礎45年化（レバー sigo）の加入可能年数 `kflcan[年度, 生年度]`（`ALL_COHORTS`）。
    canyr 年度から年度の上限が 41→45 に 3 年ごと、canyr−60 年度生から生年度の上限が 41→45 に 2 年ごとに
    上がり、両方の小さい方。それ以外は 40。港: emp_kyufu/cntl.py:set_kflcan"""
    SG = pol.get("kounen.sigo")
    canyr = int(pol.get("kounen.years.canyr"))
    T = np.full((YEARS.n, ALL_COHORTS.n), float(SG["base_years"]))
    ys = YEARS.labels()
    cs = ALL_COHORTS.labels()
    ycap = np.full(YEARS.n, np.nan)
    for off, v in sorted((int(a), float(b)) for a, b in SG["year_steps"].items()):
        ycap[ys >= canyr + off] = v
    c0 = canyr + int(SG["cohort_from_offset"])
    ccap = np.full(ALL_COHORTS.n, np.nan)
    for off, v in sorted((int(a), float(b)) for a, b in SG["cohort_steps"].items()):
        ccap[cs >= c0 + off] = v
    ok = (ys[:, None] >= canyr) & (cs[None, :] >= c0) & (ys[:, None] >= cs[None, :])
    T = np.where(ok, np.minimum(ccap[None, :], ycap[:, None]), T)
    return T


def seid_consts(pol, ad2, pseid, konen, kflcan=None, flg_sigo=0):
    """`ad2[kijun]` で基準年度価格に直す。`kflcan[cohort]` は基礎45年化のとき。"""
    R = pol.get("kounen.rates")
    T = pol.get("kounen.tables")
    A = pol.get("kounen.amounts_2004")
    kij = YEARS.i(pol.get("kounen.years.kijun"))
    c = ALL_COHORTS.labels()
    t0 = int(pol.get("kounen.tables_first_cohort"))
    nt = len(T["tmp"])
    band = (c >= t0) & (c < t0 + nt)
    ti = np.clip(c - t0, 0, nt - 1)
    pre = np.where(band, np.asarray(T["tmp"], dtype=float)[ti] * 1.0e-5, R["pre_1946"])
    pres = np.where(band, np.asarray(T["tmp2"], dtype=float)[ti] * 1.0e-6, R["pres_1946"] / R["hikrate"])
    pre[c < t0] = pre[c == t0][0]                          # 1926 年度生より前は先頭の乗率（港の pra/pras）
    pres[c < t0] = pres[c == t0][0]
    flt = np.where(band, np.asarray(T["tmq"], dtype=float)[ti] * 1.0e-3, 1.0)
    flt[c < t0] = 0.
    a2 = float(ad2[kij])
    fl1 = roundn(A["fl1"] * a2, -2)
    fl = c_round(A["fl_tanka_tsuki"] * a2) * 12.
    minb = roundn(A["minb"] * a2, -2)
    adt = np.zeros(4)
    for ii in (1, 2, 3):
        adt[ii] = roundn(A["adt"][ii - 1] * a2, -2)
    sadt = _by_cohort(pol.get("kounen.tokubetu_kasan.points"))
    sadt = np.where(sadt > 0., np.vectorize(lambda v: roundn(v * a2, -2))(sadt), 0.)
    tmr = np.asarray(T["tmr"], dtype=float)
    band_r = (c >= t0) & (c < t0 + len(tmr))
    cadt = np.where(band_r, tmr[np.clip(c - t0, 0, len(tmr) - 1)] * 1.0e-3 * adt[1], 0.)
    wif = roundn(A["wif"] * a2, -2)
    KN = pol.get("kounen.kanou_nensu")
    can = np.minimum(np.maximum(c - KN["base_cohort"], 0) + KN["base_years"], KN["max_years"]).astype(float)
    can[c < t0] = 0.
    can2 = _by_cohort(pol.get("kounen.kanou_nensu_tsuro.points"))
    can2[c < t0] = 0.
    if flg_sigo >= 1:
        canyr = pol.get("kounen.years.canyr")
        m = c >= canyr - 60
        can[m] = kflcan[m]
        can2[m] = kflcan[m]
    KF = pol.get("kounen.keikateki_kafu")
    wife = np.zeros(ALL_COHORTS.n)
    lo = c <= KN["base_cohort"]
    wife[lo] = wif
    mid = (c > KN["base_cohort"]) & (c < KF["zero_from"])
    wife[mid] = wif - fl1 * (c[mid] - KN["base_cohort"]) / can[mid]
    ha = np.zeros(4); hb = np.zeros(4); ema = np.zeros(4); emb = np.zeros(4); emc = np.zeros(4)
    ha[1:4] = R["ha"]; hb[1:4] = R["hb"]
    ema[1:3] = R["ema"]; ema[3] = ema[1]
    emb[1:3] = R["emb"]; emb[3] = emb[1]
    if flg_sigo == 2:
        emc[1:3] = R["emc"]; emc[3] = emc[1]
    ee = np.zeros(3)
    E = pol.get("kounen.dattai_ritsu")
    ee[2] = E["kiso"]
    ee[1] = E["kou"] if pseid == 0 else (E["kyosai"] if pseid <= 4 else E["sig"])
    return Seid(pre, pres, flt, fl1, fl, minb, adt, sadt, cadt, wif, wife, can, can2,
                float(R["senll"]), ha, hb, ema, emb, emc, float(R["srv"]), ee)


# ---------------------------------------------------------------- 支給率

def sik_extend(pol, sikur, pseid, flg_okure=0, flg_siktuika=0):
    """基準年度の翌年度（KS+1）の支給率を将来年度へ伸ばす → (sik, nos)。

    sik[k, x, s, i, j]（(YEARS.n, NX, 3, 20, 3)）、nos[k, x, s, i, j]（裁定遅れ）。
    i: 1〜4 老齢（退職／在職 × 新／通）、9・16 定額部分、11・17 在職、19 …、
    j: 1 受給、2 在職。`sikr` は 60歳代前半の補正、`dtem` は高齢の在職支給率の伸び。
    """
    KS = YEARS.i(pol.get("kounen.years.kijun")) - 1          # 港の KS = 20（基準年度の前年度）
    KIJ = YEARS.i(pol.get("kounen.years.kijun"))
    KE = YEARS.n - 1
    S = pol.get("kounen.sik")
    dtem_s = (None, float(pol.get("kounen.rates.dtem")[0]), float(pol.get("kounen.rates.dtem")[1]))
    xs, xe = (S["xs_kou"], S["xe_kou"]) if pseid == 0 else (S["xs_kyosai"], S["xe_kyosai"])
    fy = S["fill_years"]
    sik = np.zeros((YEARS.n, NX, 3, 20, 3))
    nos = np.zeros((YEARS.n, 70, 3, 18, 3))
    sik[KS + 1] = sikur.sik
    sikr = sikur.sikr
    nos[KS:, 60:70, 1:3, 1:18, 1:3] = 1.
    base = sikur.sik
    okure_end = KIJ + int(S["okure_years"])

    def female_kou(s):
        return pseid == 0 and s == 2

    for k in range(KS + 2, KE + 1):
        sik[k] = base
        dk = k - (KS + 1)
        for s in (1, 2):
            for j in (1, 2):
                if female_kou(s):
                    for x in range(62, NX):
                        if x - dk < 62:
                            sik[k, x, s, 9, j] = sik[k, 61, s, 9, j] if x < 65 else 1.
                            sik[k, x, s, 16, j] = sik[k, 61, s, 16, j] if x < 65 else 1.
                else:
                    for x in range(63, NX):
                        if x - dk < 63:
                            sik[k, x, s, 9, j] = sik[k, 62, s, 9, j] if x < 65 else 1.
                            sik[k, x, s, 16, j] = sik[k, 62, s, 16, j] if x < 65 else 1.
        # 在職（11・17）の 0〜18 歳は経過年で重み付け
        xx = np.arange(0, 19, dtype=float)
        w_old = np.maximum(0., xx + 1 - dk)
        w_new = np.minimum(xx + 1, dk)
        for s in (1, 2):
            for j in (1, 2):
                sik[k, 0:19, s, 11, j] = (w_old * base[0:19, s, 11, j] + w_new * 1.0) / (xx + 1)
                sik[k, 0:19, s, 17, j] = (w_old * base[0:19, s, 17, j] + w_new * sik[k, 0:19, s, 19, j]) / (xx + 1)
        # 裁定遅れ
        if flg_okure == 0 and k <= okure_end:
            for s in (1, 2):
                for i in (1, 2, 3, 4):
                    for j in (1, 2):
                        if s == 1 or (pseid != 0 and s == 2):
                            if k == KIJ + 2:
                                nos[k, 64, s, i, j] = 1. - (1. - sikr[64, s, i, j]) * (3. - (k - KIJ)) / 2.
                                sik[k, 64, s, i, j] = sik[KIJ, 64, s, i, j] * nos[k, 64, s, i, j]
                        elif k <= KIJ + 3:
                            for x in range(62, 62 + k - KIJ):
                                if k == KIJ + 3 and x == 62:
                                    continue
                                nos[k, x, s, i, j] = 1. - (1. - sikr[x, s, i, j]) * (4. - (k - KIJ)) / 3.
                                sik[k, x, s, i, j] = sik[KIJ, x, s, i, j] * nos[k, x, s, i, j]
                        if i in (2, 4):                       # 在職は 65〜69 歳も
                            if k <= KIJ + 2:
                                if s == 1 or (pseid != 0 and s == 2):
                                    if k == KIJ + 1:
                                        nos[k, 64, s, i, j] = sikr[64, s, i, j] / sikr[64 - k + KIJ, s, i, j]
                                        sik[k, 64, s, i, j] = sik[KIJ, 64, s, i, j] * nos[k, 64, s, i, j]
                                else:
                                    for x in range(62 + k - KIJ, 65):
                                        nos[k, x, s, i, j] = sikr[x, s, i, j] / sikr[x - k + KIJ, s, i, j]
                                        sik[k, x, s, i, j] = sik[KIJ, x, s, i, j] * nos[k, x, s, i, j]
                            for x in range(65, 70):
                                nos[k, x, s, i, j] = 1. - (1. - sikr[x, s, i, j]) * (6. - (k - KIJ)) / 5.
                                sik[k, x, s, i, j] = sik[KIJ, x, s, i, j] * nos[k, x, s, i, j]
        # 年齢を1つずらして持ち越す給付（i = 5〜13, 18）
        if not (pseid == 0 and k == KS + 2):
            for i in (5, 6, 7, 8):                      # 旧法は 46 歳から
                sik[k, 46:NX, 1:3, i, 1:3] = sik[k - 1, 45:NX - 1, 1:3, i, 1:3]
            for i in (10, 12, 13, 18):                  # 9・11 は動かさない（港のまま）
                sik[k, 66:NX, 1:3, i, 1:3] = sik[k - 1, 65:NX - 1, 1:3, i, 1:3]
        # 支給開始年齢の段差を埋める。i の組ごとに 61 歳から引く性が入れ替わる（厚年だけ）
        for grp, flip in (((9, 10, 16), 2), ((11, 12, 13), 1), ((1, 2, 3, 4), 2)):
            for i in grp:
                for s in (1, 2):
                    if pseid == 0 and s == flip:
                        F = fy["kou_from_61"]
                        for x in (62, 63, 64):
                            if k >= YEARS.i(F[str(x)]):
                                sik[k, x, s, i, :] = sik[k, 61, s, i, :]
                    else:
                        F = fy["from_62"]
                        for x in (63, 64):
                            if k >= YEARS.i(F[str(x)]):
                                sik[k, x, s, i, :] = sik[k, 62, s, i, :]
        # 高齢の在職支給率の外挿
        for x in range(xs, NX):
            if x <= 65 + k - 7:
                for s in (1, 2):
                    if x == xs:
                        sik[k, x, s, 11, 1] = sik[k, xs - 1, s, 11, 1] * 2. - sik[k, xs - 2, s, 11, 1]
                    elif x <= xe:
                        sik[k, x, s, 11, 1] = base[min(x, xe), s, 11, 1] * (sik[k, xs, s, 11, 1] / base[xs, s, 11, 1])
                    else:
                        sik[k, x, s, 11, 1] = min(max(sik[k, x - 1, s, 11, 1] * 2. - sik[k, x - 2, s, 11, 1],
                                                      sik[k, x - 1, s, 11, 1]), 1.)
                    sik[k, x, s, 1:5, 1:3] = sik[k - 1, x - 1, s, 1:5, 1:3]
            elif x <= 95 + k - (KS + 1):
                for s in (1, 2):
                    sik[k, x, s, 11, 1] = max(sik[k - 1, x - 1, s, 11, 1] * dtem_s[s],
                                              base[min(x, xe), s, 11, 1] * sik[k, xs, s, 11, 1] / base[xs, s, 11, 1])
    # 繰上げ・繰下げによる在職（新通）の減額（厚年だけ。共済は 1.0）
    if flg_siktuika == 0 and pseid == 0:
        G = S["tsuro_gen"]
        x = np.arange(NX)
        for k in range(KIJ + 1, KE + 1):
            a = x - (k - KIJ)                       # 基準年度時点の年齢
            d1 = np.ones(NX); d2 = np.ones(NX)
            young = (a >= 23) & (a <= 59)
            d2[young] = G["young_female"][0] + (G["young_female"][1] - G["young_female"][0]) / 36. * (a[young] - 23)
            older = (a >= 61) & (a <= 69)
            d1[older] = G["sixties_male"][0] + (G["sixties_male"][1] - G["sixties_male"][0]) / 8. * (a[older] - 61)
            d2[older] = G["sixties_female"][0] + (G["sixties_female"][1] - G["sixties_female"][0]) / 8. * (a[older] - 61)
            if k <= okure_end:
                sixties = (a >= 60) & (a <= 69)
                d1[sixties] = 1. - (1. - d1[sixties]) / 5. * (k - KIJ)
                d2[sixties] = 1. - (1. - d2[sixties]) / 5. * (k - KIJ)
            for i in (3, 4):
                sik[k, :, 1, i, 2] *= d1
                sik[k, :, 2, i, 2] *= d2
    return sik, nos


# ---------------------------------------------------------------- 報酬水準

@dataclass
class Hoshu:
    br: np.ndarray            # (YEARS.n, NX, 4) 20歳を 1 とした報酬指数
    bn: np.ndarray            # (YEARS.n, NX, 4) 標準報酬（年額）
    bnpt: np.ndarray          # (YEARS.n, NX, 3) パートの平均報酬（基準年度価格）
    dmpt2: np.ndarray
    partbbn: np.ndarray       # (2, 2, 11, 3) パートの報酬（0 現行 / 1 拡大後; 年齢帯 x ≤ 59 / ≥ 60; 性）


def set_hsr(pol, hou, l, ad, pseid, flg_part=0, flg_hiho70=0, lpt=None, lpt2=None, lpt3=None, lpt4=None):
    """`hou`: `Hou`（BR・BN・BNPTI）、`l[k, s, x]` 被保険者数、`ad` 賃金の累積。
    `flg_part ≥ 1`（適用拡大のレバー）なら `lpt`（パート全体）と増分 `lpt2/3/4` から、オプションの
    年度（`kounen.years.part_yr_option`）以降のパートの標準報酬 `bnpt` と按分用 `dmpt2` を作る。"""
    KS = YEARS.i(pol.get("kounen.years.kijun")) - 1
    KE = YEARS.n - 1
    hsr_endy = YEARS.i(pol.get("kounen.years.hsr_endy"))
    hsr_r = float(pol.get("kounen.rates.hsr_r"))
    xmax = 84 if pseid == 0 else 74
    ns = 3 if pseid == 0 else 2
    br = np.zeros((YEARS.n, NX, 4)); bn = np.zeros((YEARS.n, NX, 4))
    br[KS, 15:xmax + 1, 1:ns + 1] = hou.br[15:xmax + 1, 1:ns + 1]
    bn[KS, 15:xmax + 1, 1:ns + 1] = hou.bn[15:xmax + 1, 1:ns + 1]
    br[KS + 1, 15:85] = br[KS, 15:85]
    bn[KS + 1, 15:85] = bn[KS, 15:85]
    if pseid == 0:
        xr = slice(15, 85)
        for k in range(KS + 2, KE + 1):
            if k <= hsr_endy:
                b1 = bn[k - 1, xr, 1]; b2 = bn[k - 1, xr, 2]
                l1 = l[k, 1, xr]; l2 = l[k, 2, xr]
                tml = l1 + l2
                pos = tml > 0.
                w1 = np.where(pos, l2 / np.where(pos, tml, 1.), 0.5)
                w2 = np.where(pos, l1 / np.where(pos, tml, 1.), 0.5)
                bn[k, xr, 1] = b1 - w1 * hsr_r * (b1 - b2)
                bn[k, xr, 2] = b2 + w2 * hsr_r * (b1 - b2)
            else:
                bn[k, xr, 1:3] = bn[k - 1, xr, 1:3]
            bn[k, xr, 3] = bn[k - 1, xr, 3]
            br[k, xr, 1:4] = bn[k, xr, 1:4] / bn[KS + 1, 20, 1:4]
    else:
        br[KS + 2:, 15:85, 1:3] = br[KS + 1, 15:85, 1:3]
        bn[KS + 2:, 15:85, 1:3] = bn[KS + 1, 15:85, 1:3]
    P = pol.get("kounen.part.bbn_tsuki")
    partbbn = np.zeros((2, 2, 11, 3))
    for s in (1, 2):
        partbbn[0, 0, 1:3, s] = P["0"][s - 1] * 12.          # 男女別（年齢帯 1・2 は同じ）
        if flg_part >= 1:
            partbbn[1, 0, 1:3, s] = P[str(flg_part)][s - 1] * 12.   # 適用拡大の案ごとの標準報酬
    bnpt = np.zeros((YEARS.n, NX, 3)); dmpt2 = np.zeros((YEARS.n, NX, 3))
    if pseid == 0:
        a22 = ad[YEARS.i(pol.get("kounen.years.part_yr2"))]
        p3 = YEARS.i(pol.get("kounen.years.part_yr3"))
        x = np.arange(15, 85)
        for s in (1, 2):
            v = np.where(x <= 59, partbbn[0, 0, 1, s], partbbn[0, 0, 2, s]) / a22
            bnpt[KS:, 15:85, s] = v
            dmpt2[p3 - 1, 15:85, s] = v
            dmpt2[p3, 15:85, s] = v
            if flg_part >= 1:
                p4 = YEARS.i(pol.get("kounen.years.part_yr_option"))
                v0 = np.where(x <= 59, partbbn[0, 0, 1, s], partbbn[0, 0, 2, s])
                v1 = np.where(x <= 59, partbbn[1, 0, 1, s], partbbn[1, 0, 2, s])
                bi = hou.bnpti[15:85, s]
                L2, L3, L4, L = (a[KS:, s, 15:85] for a in (lpt2, lpt3, lpt4, lpt))
                sum3 = L2 + L3 + L4
                with np.errstate(divide="ignore", invalid="ignore"):
                    at = np.where(sum3 > _EPS_PART, (L2 * bi + (L3 + L4) * v1) / sum3 / a22, 0.)
                    after = np.where(L > _EPS_PART, (L2 * bi + (L3 + L4) * v1 + (L - sum3) * v0) / L / a22, 0.)
                bnpt[p4, 15:85, s] = at[p4 - KS]
                bnpt[p4 + 1:, 15:85, s] = after[p4 + 1 - KS:]
                for k in (p4 - 1, p4):
                    dmpt2[k, 15:85, s] = np.where(sum3[k - KS] > _EPS_PART, at[k - KS], dmpt2[k, 15:85, s])
        if flg_hiho70 == 0:
            bn[KS:, 70:85, 1:4] = 0.
            bnpt[KS:, 70:85, 1:3] = 0.
    return Hoshu(br, bn, bnpt, dmpt2, partbbn)
