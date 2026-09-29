# -*- coding: utf-8 -*-
"""③の給付 — 新規発生と年度末（§5.1〜5.3）
===========================================
給付ごとに「新規発生」と「年度末」を書く。年度末は共通の形

    年度末[y, x, …] = adjustbenefit(改定率[y, x], (1 − 失権率[y, x]) · 年度末[y−1, x−1, …]) + 新規[y, x, …]

（前年度の1歳下を読んで当年度に書く。人数と付加年金は改定しない）。
配列は AGES の軸 × 追加の軸（繰上げ・繰下げ区分 11、障害等級 3）× 欄。

遺族の 60〜64歳の枝で引く生命表は呼び手が選ぶ（既定は原本どおりの B11。`run.py:izoku_lifetable`）。

港: nat/siml.py:siml
仕様: §5.1、§5.2、§5.3、§7.3
"""
from dataclasses import dataclass, field

import numpy as np

from ...algebra import adjustbenefit
from ...axis import AGES, YEARS, COHORTS
from .layouts import (HIHOKENSHA, ROREI, ROREI_KYU, GONEN, SHOGAI, IZOKU, KAFU, ICHIJIKIN,
                      MENJO_DANKAI, KOKKO_KUBUN)
from .transition import A as HIHO_AGES, K, AGE_MIN as HIHO_MIN, AGE_MAX as HIHO_MAX

__all__ = ["NatState", "Shinki", "KURIAGE_N", "ROREI_MIN", "ROREI_MAX", "TOKYU_N",
           "sotowaku4", "bunpu_weights", "shinki_shogai", "shinki_izoku", "shinki_kafu",
           "shinki_ichijikin", "shinki_rorei", "yearend_rorei", "yearend_shogai",
           "yearend_izoku", "yearend_kafu"]

ROREI_MIN, ROREI_MAX = 60, 115       # 老齢の受給年齢
KURIAGE_N = 11                       # 受給開始年齢 60〜70 の区分
SHOGAI_MIN, SHOGAI_MAX = 20, 115
TOKYU_N = 3                          # 添字 1・2 だけ使う（0 は計）
TUMA_MIN, OTTO_MIN, KO_MIN, KO_MAX = 16, 18, 0, 19
IZOKU_MAX = 115                      # 妻・夫の受給年齢の上限（港: MAX_IZOKU_TUMA_JUKYU）
KAFU_MIN, KAFU_MAX = 26, 64

# 欄の添字
H_NINZU, H_NOUFU, H_GAKUSEI, H_WAKAMONO, H_FUKA = (HIHOKENSHA.i(n) for n in
                                                    ("ninzu", "noufu", "gakusei", "wakamono", "fuka"))
H_MENJO = np.array([[HIHOKENSHA.i("menjo[%d][%d]" % (d, k)) for k in range(KOKKO_KUBUN)]
                    for d in range(MENJO_DANKAI)])        # (5, 3)
R_NINZU, R_NOUFU, R_FUKA = ROREI.i("ninzu"), ROREI.i("noufu"), ROREI.i("fuka")
R_MENJO = np.array([[ROREI.i("menjo[%d][%d]" % (d, k)) for k in range(KOKKO_KUBUN)]
                    for d in range(MENJO_DANKAI)])
KF_MENJO = np.array([[KAFU.i("menjo[%d][%d]" % (d, k)) for k in range(KOKKO_KUBUN)]
                     for d in range(MENJO_DANKAI)])
S_NINZU, S_KIHON, S_KAKYU, S_MKIHON, S_MKAKYU = range(5)
I_NINZU, I_KIHON, I_KAKYU = range(3)


@dataclass
class NatState:
    """ある年度末の全部の状態（1つの被保険者区分）。"""
    hiho: object                                         # transition.HihoState
    rorei: np.ndarray = field(default_factory=lambda: np.zeros((AGES.n, KURIAGE_N, ROREI.n)))
    rorei_ichibu: np.ndarray = field(default_factory=lambda: np.zeros((AGES.n, KURIAGE_N, ROREI.n)))
    rorei_kyu: np.ndarray = field(default_factory=lambda: np.zeros((AGES.n, KURIAGE_N, ROREI_KYU.n)))
    turo_kyu: np.ndarray = field(default_factory=lambda: np.zeros((AGES.n, KURIAGE_N, ROREI_KYU.n)))
    gonen: np.ndarray = field(default_factory=lambda: np.zeros((AGES.n, KURIAGE_N, GONEN.n)))
    shogai_ippan: np.ndarray = field(default_factory=lambda: np.zeros((AGES.n, TOKYU_N, SHOGAI.n)))
    shogai_20mae: np.ndarray = field(default_factory=lambda: np.zeros((AGES.n, TOKYU_N, SHOGAI.n)))
    shogai_kyu: np.ndarray = field(default_factory=lambda: np.zeros((AGES.n, TOKYU_N, SHOGAI.n)))
    izoku_tuma: np.ndarray = field(default_factory=lambda: np.zeros((AGES.n, IZOKU.n)))
    izoku_otto: np.ndarray = field(default_factory=lambda: np.zeros((AGES.n, IZOKU.n)))
    izoku_ko: np.ndarray = field(default_factory=lambda: np.zeros((AGES.n, IZOKU.n)))
    kafu: np.ndarray = field(default_factory=lambda: np.zeros((AGES.n, KAFU.n)))
    kafu_kyu: np.ndarray = field(default_factory=lambda: np.zeros((AGES.n, KAFU.n)))
    ichijikin: np.ndarray = field(default_factory=lambda: np.zeros((AGES.n, ICHIJIKIN.n)))


@dataclass
class Shinki:
    """当年度の新規発生（年度末に足す前）。"""
    rorei: np.ndarray            # (KURIAGE_N, ROREI.n)  受給開始年齢ごと
    shogai_ippan: np.ndarray     # (AGES.n, TOKYU_N, SHOGAI.n)
    shogai_20mae: np.ndarray
    izoku_tuma: np.ndarray       # (AGES.n, IZOKU.n)  受給者の年齢
    izoku_otto: np.ndarray
    izoku_ko: np.ndarray
    kafu: np.ndarray             # (AGES.n, KAFU.n)


def sotowaku4(pop, yi, ages):
    """外枠（人口）の4点平均。`pop[YEARS, AGES]`。港: nat/siml.py:siml（`_sotowaku4`）

        ( pop[y−1][x−2] + pop[y−1][x−1] + pop[y][x−1] + pop[y][x] ) / 4
    """
    ai = AGES.i(np.asarray(ages))
    return (pop[yi - 1, ai - 2] + pop[yi - 1, ai - 1] + pop[yi, ai - 1] + pop[yi, ai]) / 4.


def bunpu_weights(sokan, lo, hi):
    """相関（平均年齢差）から受給者の年齢の重み (len(sokan), AGES.n)。
    `sokan[i]` の整数部 k に (k+1−s)、k+1 に (s−k) を置き、ほかは 0。
    港: nat/siml.py:siml（`_bunpu`）"""
    sokan = np.asarray(sokan, dtype=np.float64)
    w = np.zeros((sokan.size, AGES.n))
    k = np.floor(sokan).astype(int)
    frac = sokan - k
    for i in range(sokan.size):
        if lo <= k[i] <= hi:
            w[i, AGES.i(k[i])] += 1. - frac[i]
        if lo <= k[i] + 1 <= hi:
            w[i, AGES.i(k[i] + 1)] += frac[i]
    return w


# ---------------------------------------------------------------- 新規発生

def shinki_shogai(rates, yi, cls, flows, pop, gou2, mangaku, bairitu):
    """障害基礎（20歳前・一般）の新規発生。

    20歳前（第1号のみ）: 人口の4点平均 × 発生割合 × 等級割合
    一般: 60歳未満は前年度の被保険者 × 発生力（`flows.hasseisha_shogai`）× 等級割合、
          60歳以上（第1号のみ）は (人口4点平均 − 前年度の第2号[x−1]) × 発生力 × 等級割合
    年金額 = 人数 × 満額[y, x] × 等級倍率
    """
    ippan = np.zeros((AGES.n, TOKYU_N, SHOGAI.n))
    mae = np.zeros((AGES.n, TOKYU_N, SHOGAI.n))
    ages = np.arange(HIHO_MIN, HIHO_MAX + 1)
    ai = AGES.i(ages)
    p4 = sotowaku4(pop, yi, ages)
    fp = mangaku[yi, ai]
    for t in (1, 2):
        if cls.gou == 1:
            n = p4 * rates.hassei_20mae[yi, ai] * rates.tokyu_20mae[yi, t]
            mae[ai, t, S_NINZU] = n
            mae[ai, t, S_KIHON] = n * fp * bairitu[t]
        n = flows.hasseisha_shogai[ai].sum(axis=1) * rates.tokyu_ippan[yi, t]
        n = np.where(ages < 60, n, 0.)
        if cls.gou == 1:
            over = ages >= 60
            n = np.where(over, (p4 - gou2[yi - 1, ai - 1]) * rates.hasseiryoku_shogai[yi, ai]
                         * rates.tokyu_ippan[yi, t], n)
        ippan[ai, t, S_NINZU] = n
        ippan[ai, t, S_KIHON] = n * fp * bairitu[t]
    return ippan, mae


def _izoku_one(rates, yi, cls, flows, pop, gou2, q, mangaku, sokan, hassei, lo, hi, do_60_64):
    """遺族（妻・夫・子）の新規発生の共通形。受給者の年齢 (AGES.n, IZOKU.n)。"""
    out = np.zeros((AGES.n, IZOKU.n))
    ages = np.arange(HIHO_MIN, HIHO_MAX + 1)
    ai = AGES.i(ages)
    w = bunpu_weights(sokan[yi, ai], lo, hi)            # (51, AGES.n)
    fp = mangaku[yi, ai]
    h = hassei[yi, ai]
    dead = flows.hiho_shibou[ai, :, H_NINZU].sum(axis=1)  # 被保険者の死亡（期間の和）
    base = np.where(ages < 60, dead * h, 0.)
    if do_60_64:
        p4 = sotowaku4(pop, yi, ages)
        m = (ages >= 60) & (ages <= 64)
        yq = min(yi, YEARS.i(rates.lifetable_last))
        base = base + np.where(m, (p4 - gou2[yi - 1, ai - 1]) * q[yq, ai] * h, 0.)
    out[:, I_NINZU] = base @ w
    out[:, I_KIHON] = (base * fp) @ w
    return out


def shinki_izoku(rates, yi, cls, flows, pop, gou2, lifetable_q, mangaku):
    """遺族基礎の新規発生。妻・子は第1号男だけ、夫は女（60〜64歳の枝は第1号女だけ）。
    `lifetable_q` は 60〜64歳の枝で引く表（`run.py:izoku_lifetable` が B11 の切り替えで選ぶ）。"""
    z = np.zeros((AGES.n, IZOKU.n))
    tuma = otto = ko = z
    if cls.sex == "male" and cls.gou == 1:
        tuma = _izoku_one(rates, yi, cls, flows, pop, gou2, lifetable_q, mangaku,
                          rates.sokan_tuma, rates.hassei_tuma, TUMA_MIN, IZOKU_MAX, True)
        ko = _izoku_one(rates, yi, cls, flows, pop, gou2, lifetable_q, mangaku,
                        rates.sokan_ko, rates.hassei_ko, KO_MIN, KO_MAX, True)
    if cls.sex == "female":
        otto = _izoku_one(rates, yi, cls, flows, pop, gou2, lifetable_q, mangaku,
                          rates.sokan_otto, rates.hassei_otto, OTTO_MIN, IZOKU_MAX, cls.gou == 1)
    return tuma, otto, ko


def shinki_kafu(rates, yi, cls, flows, mangaku, kanou_nensu, hokenryou_wariai, kokko_wariai):
    """寡婦年金の新規発生（第1号男だけ）。納付期間10年以上の死亡者から。

        人数  += 死亡者数 × 発生割合 × 年齢の重み
        納付分 += 3/4 × 満額 × (納付月数 + Σ β_d 免除月数) / 加入可能年数 × …
        免除分[d][k] += 3/4 × γ_k (1 − β_d) 満額 × 免除月数[d][k] / 加入可能年数 × …
    """
    out = np.zeros((AGES.n, KAFU.n))
    if not (cls.sex == "male" and cls.gou == 1):
        return out
    ages = np.arange(HIHO_MIN, HIHO_MAX + 1)
    ai = AGES.i(ages)
    year = YEARS.label(yi)
    w = bunpu_weights(rates.sokan_kafu[yi, ai], KAFU_MIN, KAFU_MAX)   # (51, AGES.n)
    fp = mangaku[yi, ai][:, None]
    h = rates.hassei_kafu[yi, ai][:, None]
    kn = kanou_nensu[yi, COHORTS.i(year - ages)][:, None]            # 生年度で引く
    beta = np.asarray(hokenryou_wariai)                              # (5,) 段階別
    gamma = np.asarray(kokko_wariai)                                 # (3,) 国庫区分別
    for src in (flows.hiho_shibou, flows.taiki_shibou):
        rec = src[ai]                                                # (51, K, 21)
        mj = rec[:, :, H_MENJO[1:, 1:]]                              # (51, K, 4, 2)
        noufu_kikan = (rec[:, :, H_NOUFU] + rec[:, :, H_GAKUSEI] + rec[:, :, H_WAKAMONO]
                       + mj.sum(axis=(2, 3)))
        ok = noufu_kikan >= 10.
        base = np.where(ok, rec[:, :, H_NINZU], 0.) * h              # (51, K)
        out[:, 0] += base.sum(axis=1) @ w
        noufu = 0.75 * fp * rec[:, :, H_NOUFU] / kn * base
        noufu = noufu + (0.75 * fp[:, :, None, None] * beta[None, None, 1:, None] * mj
                         / kn[:, :, None, None] * base[:, :, None, None]).sum(axis=(2, 3))
        out[:, KAFU.i("noufu")] += noufu.sum(axis=1) @ w
        menjo = (0.75 * gamma[None, None, None, 1:] * (1. - beta[None, None, 1:, None])
                 * fp[:, :, None, None] * mj / kn[:, :, None, None] * base[:, :, None, None])
        menjo = menjo.sum(axis=1)                                    # (51, 4, 2)
        for d in range(1, MENJO_DANKAI):
            for k in range(1, KOKKO_KUBUN):
                out[:, KF_MENJO[d, k]] += menjo[:, d - 1, k - 1] @ w
    return out


def shinki_ichijikin(rates, yi, cls, flows, nj, hokenryou_wariai, tanka_shibou, tanka_fuka,
                     shibou_kubun):
    """死亡一時金（第1号だけ）。納付期間3年以上の死亡者。港: nat/siml.py:siml, Shibou_Kubun"""
    out = np.zeros((AGES.n, ICHIJIKIN.n))
    if cls.gou != 1:
        return out
    ages = np.arange(HIHO_MIN, HIHO_MAX + 1)
    ai = AGES.i(ages)
    beta = np.asarray(hokenryou_wariai)
    h = rates.hassei_shibou[yi, ai][:, None]
    nj_fuka = nj[ai, H_FUKA][:, None]
    for src in (flows.hiho_shibou, flows.taiki_shibou):
        rec = src[ai]
        mj = rec[:, :, H_MENJO[1:, 1:]]                              # (51, K, 4, 2)
        noufu_kikan = rec[:, :, H_NOUFU] + (mj * beta[None, None, 1:, None]).sum(axis=(2, 3))
        with np.errstate(divide="ignore", invalid="ignore"):
            fuka_kikan = np.where(nj_fuka == 0., 0., rec[:, :, H_FUKA] / nj_fuka)
        ok = noufu_kikan >= 3.
        n = np.where(ok, rec[:, :, H_NINZU] * h, 0.)
        kubun = shibou_kubun(noufu_kikan)                            # (51, K) の区分
        tanka = tanka_shibou[kubun]
        out[ai, 0] += n.sum(axis=1)
        out[ai, 1] += (tanka * n).sum(axis=1)
        out[ai, 2] += np.where(fuka_kikan >= 3., tanka_fuka * n * nj_fuka, 0.).sum(axis=1)
    return out


def shinki_rorei(rates, yi, cls, hiho, mangaku, kanou_nensu, kyufu_ritu, fuka_tanka,
                 hokenryou_wariai, kokko_wariai, kakudai_extra=None):
    """老齢基礎の新規裁定（待期者から。**待期者の人数をその場で減らす**）。

        新規[j] = Σ_t 待期者[x=60+j, t] × 発生割合[y, j]
        納付分  = 満額 × 給付率 × (納付月数 + Σ β_d 免除月数[d][k]) / 加入可能年数 × 人数 × 発生割合
        免除分[d][k] = 満額 × 給付率 × γ_k (1 − β_d) × 免除月数[d][k] / 加入可能年数 × …
        付加    = 2,400 × 給付率 × 付加年数 × 人数 × 発生割合
    港: nat/siml.py:siml（`_rorei_shinki`）  仕様: §5.1、§5.2
    """
    out = np.zeros((KURIAGE_N, ROREI.n))
    year = YEARS.label(yi)
    beta = np.asarray(hokenryou_wariai)
    gamma = np.asarray(kokko_wariai)
    T = hiho.T
    for j in range(KURIAGE_N):
        x = ROREI_MIN + j
        xi = AGES.i(x)
        cohort = year - x
        fp = mangaku[yi, xi]
        kr = kyufu_ritu(j, cohort, cls.sex)
        kn = kanou_nensu[yi, COHORTS.i(cohort)]
        hw = rates.hassei_rorei[yi, j]
        rec = T[xi]                                                  # (K, 21)
        n = rec[:, H_NINZU] * hw                                     # (K,)
        mj = rec[:, H_MENJO[1:, 1:]]                                 # (K, 4, 2)
        out[j, R_NINZU] += n.sum()
        noufu = fp * kr * rec[:, H_NOUFU] / kn * n
        noufu = noufu + (fp * kr * beta[None, 1:, None] * mj / kn * n[:, None, None]).sum(axis=(1, 2))
        out[j, R_NOUFU] += noufu.sum()
        menjo = (fp * kr * gamma[None, None, 1:] * (1. - beta[None, 1:, None]) * mj / kn
                 * n[:, None, None]).sum(axis=0)                     # (4, 2)
        for d in range(1, MENJO_DANKAI):
            for k in range(1, KOKKO_KUBUN):
                out[j, R_MENJO[d, k]] += menjo[d - 1, k - 1]
        out[j, R_FUKA] += (fuka_tanka * kr * rec[:, H_FUKA] * n).sum()
        T[xi, :, H_NINZU] *= (1. - hw)
    return out


# ---------------------------------------------------------------- 年度末

def _carry(layout, prev, zan, kt, lo, hi):
    """`adjustbenefit(kt[x], (1 − 失権率[x]) · prev[x−1])` を lo+1〜hi 歳に。
    `prev[AGES.n, …, slots]`、`zan[AGES.n]`、`kt[AGES.n]`。lo 歳は 0。"""
    out = np.zeros_like(prev)
    src = prev[AGES.i(lo):AGES.i(hi)]                                # x−1 = lo … hi−1
    dst = slice(AGES.i(lo + 1), AGES.i(hi) + 1)
    shape = (src.shape[0],) + (1,) * (src.ndim - 1)
    z = zan[dst].reshape(shape)
    k = kt[dst].reshape(shape)
    out[dst] = adjustbenefit(layout, k, src * z)
    return out


def yearend_rorei(state_prev, shinki, yi, rates, kt_row, kakudai_row):
    """老齢基礎（新法・一部繰上げ・旧法・通算・5年）の年度末。
    新規裁定は年齢 = 受給開始年齢 の対角に足す。65歳の一部繰上げ拡大は
    生年度で決まるコホートだけ `kakudai_row`（(KURIAGE_N, ROREI.n) の係数）を掛ける。"""
    zan = 1. - rates.shikken_rorei[yi]
    out = {}
    for name, layout in (("rorei", ROREI), ("rorei_ichibu", ROREI), ("rorei_kyu", ROREI_KYU),
                         ("turo_kyu", ROREI_KYU), ("gonen", GONEN)):
        out[name] = _carry(layout, getattr(state_prev, name), zan, kt_row, ROREI_MIN, ROREI_MAX)
    if kakudai_row is not None:
        out["rorei_ichibu"][AGES.i(65)] *= kakudai_row
    for j in range(KURIAGE_N):
        out["rorei"][AGES.i(ROREI_MIN + j), j] += shinki.rorei[j]
    return out


def yearend_shogai(state_prev, shinki_ippan, shinki_mae, yi, rates, kt_row, k12_row, k3_row):
    """障害基礎（一般・20歳前・旧法）の年度末。加給は人数 × (単価12歳未満 × 割合 + 単価3子以降 × 割合)
    で毎年作り直す。旧法の加給は前年度分と「一般の割合で作った額」の小さい方、免除の加給は
    前年度の加給に対する比で按分。"""
    zan_ip = 1. - rates.shikken_ippan[yi]
    zan_20 = 1. - rates.shikken_20mae[yi]
    ip = _carry(SHOGAI, state_prev.shogai_ippan, zan_ip, kt_row, SHOGAI_MIN, SHOGAI_MAX) + shinki_ippan
    mae = _carry(SHOGAI, state_prev.shogai_20mae, zan_20, kt_row, SHOGAI_MIN, SHOGAI_MAX) + shinki_mae
    kyu = _carry(SHOGAI, state_prev.shogai_kyu, zan_ip, kt_row, SHOGAI_MIN, SHOGAI_MAX)
    lo, hi = AGES.i(SHOGAI_MIN), AGES.i(SHOGAI_MAX) + 1
    w_ip = (k12_row * rates.kakyu_ippan_12[yi] + k3_row * rates.kakyu_ippan_3[yi])[lo:hi, None]
    w_20 = (k12_row * rates.kakyu_20mae_12[yi] + k3_row * rates.kakyu_20mae_3[yi])[lo:hi, None]
    ip[lo:hi, :, S_KAKYU] = ip[lo:hi, :, S_NINZU] * w_ip
    mae[lo:hi, :, S_KAKYU] = mae[lo:hi, :, S_NINZU] * w_20
    temp = kyu[lo:hi, :, S_NINZU] * w_ip
    kk = kyu[lo:hi, :, S_KAKYU]
    kyu[lo:hi, :, S_KAKYU] = np.where(kk < temp, kk, temp)
    zen = np.zeros_like(kyu)
    zen[lo + 1:hi] = state_prev.shogai_kyu[lo:hi - 1]              # 前年度の1歳下
    zk = zen[lo:hi, :, S_KAKYU]
    with np.errstate(divide="ignore", invalid="ignore"):
        mk = kyu[lo:hi, :, S_KAKYU] * zen[lo:hi, :, S_MKAKYU] / zk
    kyu[lo:hi, :, S_MKAKYU] = np.where(zk == 0., 0., mk)
    return ip, mae, kyu


def _izoku_yearend(prev, shinki, zan, kt_row, k12_row, k3_row, w12, w3, lo, hi):
    out = _carry(IZOKU, prev, zan, kt_row, lo, hi) + shinki
    s = slice(AGES.i(lo), AGES.i(hi) + 1)
    out[s, I_KAKYU] = out[s, I_NINZU] * (k12_row[s] * w12[s] + k3_row[s] * w3[s])
    return out


def yearend_izoku(state_prev, sh_tuma, sh_otto, sh_ko, yi, rates, kt_row, k12_row, k3_row):
    """遺族基礎（妻・夫・子）の年度末。"""
    tuma = _izoku_yearend(state_prev.izoku_tuma, sh_tuma, 1. - rates.shikken_tuma[yi], kt_row,
                          k12_row, k3_row, rates.kakyu_tuma_12[yi], rates.kakyu_tuma_3[yi],
                          TUMA_MIN, IZOKU_MAX)
    otto = _izoku_yearend(state_prev.izoku_otto, sh_otto, 1. - rates.shikken_otto[yi], kt_row,
                          k12_row, k3_row, rates.kakyu_otto_12[yi], rates.kakyu_otto_3[yi],
                          OTTO_MIN, IZOKU_MAX)
    ko = _izoku_yearend(state_prev.izoku_ko, sh_ko, 1. - rates.shikken_ko[yi], kt_row,
                        k12_row, k3_row, rates.kakyu_ko_12[yi], rates.kakyu_ko_3[yi],
                        KO_MIN, KO_MAX)
    return tuma, otto, ko


def yearend_kafu(state_prev, shinki, yi, rates, kt67):
    """寡婦年金（新法・旧法）の年度末。改定率は 67歳未満のものを全年齢に。"""
    zan = 1. - rates.shikken_kafu[yi]
    kt = np.full(AGES.n, kt67)
    kafu = _carry(KAFU, state_prev.kafu, zan, kt, KAFU_MIN, KAFU_MAX) + shinki
    kyu = _carry(KAFU, state_prev.kafu_kyu, zan, kt, KAFU_MIN, KAFU_MAX)
    return kafu, kyu
