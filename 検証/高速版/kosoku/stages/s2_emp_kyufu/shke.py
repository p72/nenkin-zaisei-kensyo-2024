# -*- coding: utf-8 -*-
"""②の 1 年度ぶんの集計（移植版 `shke.cpp` と `shkehiho/shkejken/shkejsha/shkejuk/shkekiso`）
===============================================================================================
年度 `k`・種別 `s` の状態（`State`）から、⑤と④へ渡す集計を作る。

    shkehiho   被保険者数（`ap*`）・標準報酬総額（`a*`）・育休免除分（`aiku`）・適用拡大分（`*part`）
    shkejken   受給**権**者の人数 `t4k` と 1 人あたり年金額 `t6k`（減額前・加算前の額に
               繰上げ減額率・加給対象者割合・有子割合を掛け直す）
    shkejsha   支給率（`sik`）を掛けて受給者 `t4` `t6` にする。事故等の補正・裁定遅れ
    shkejuk    給付費の表 `d3x`（受給者）`d3xs`（受給権者）の列へ足す
    shkekiso   ④基礎年金へ渡す受給者数 `okisor` と給付費 `okiso2x`

移植版は (i, xx, x) の 8,395 回の関数呼び出し。高速版は給付 `i` ごとに (x, xx) をまとめる。

港の癖で残すもの（`検証/原本の不具合.md`）: E26 — i ≥ 5 の加給の判定に使う支給開始年齢
`xxr` が「直前の呼び出し（i = 4, x = 114）の値」のまま。高速版は yaml
`kounen.shke.e26_stale_xxr_age` で「114 歳の生年の支給開始年齢」として明示する。
J2（地共済の `ab` の係数 461.6518）は既定では**原本どおり**。`fix_bugs` で 0.4616518 に直る
（yaml `kounen.siml.shke.ab_factor`。桁だけを直した推定値で、意図した値は確かめられない）。

港: emp_kyufu/shke.py:shke
仕様: §5.7（受給者の集計）、§7.2（⑤への受け渡し）、§7.3（④への受け渡し）
"""
from dataclasses import dataclass, field, fields

import numpy as np

from ...axis import YEARS
from .context import cohort_index
from .inputs import NX, NT, NXX, NI, NJ
from .siml import _rnd

__all__ = ["Agg", "new_agg", "shke", "shkehiho", "shkejken", "shkejsha", "shkejuk", "shkekiso",
           "D3X_COLS", "D3XS_COLS", "jikoutou_rates"]

# 出力に要る d3x の列（0 人数、7〜12 給付費の内訳、13〜18 国庫負担の算定対象、22〜25 加算）
D3X_COLS = (0, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 22, 23, 24, 25)
# 老先振替（rousaki）が読む d3xs の列
D3XS_COLS = (7, 8, 9, 10, 11, 13, 17)
_C = {j: n for n, j in enumerate(D3X_COLS)}
_CS = {j: n for n, j in enumerate(D3XS_COLS)}
_EPS = 1.0e-6
_A_NAMES = ("ap", "apdum", "appart", "appartdum", "ap65", "ap65dum", "appart65", "appart65dum",
            "ap70", "ap70dum", "appart70", "appart70dum", "ap75", "ap75dum", "appart75", "appart75dum",
            "ap85", "ap85dum", "appart85", "appart85dum",
            "a", "adum", "aiku", "aikudum", "a60", "a60dum", "a65", "a65dum", "a70", "a70dum",
            "a75", "a75dum", "a85", "a85dum", "apart", "aikupart", "a60part", "a65part", "a70part",
            "a75part", "a85part", "aal", "at")


@dataclass
class Agg:
    """1 制度ぶんの集計（種別を通して積む）。年度 × 性（0 計 / 1 男 / 2 女 / 3 3号）。"""
    ks: dict = field(default_factory=dict)             # _A_NAMES → (YEARS.n, 4)
    gee: np.ndarray = None                             # (YEARS.n, 4, NX, 71)
    geept: np.ndarray = None
    d3x: np.ndarray = None                             # (YEARS.n, NX, 4, NI, len(D3X_COLS))
    d3xs: np.ndarray = None                            # (YEARS.n, NX, 4, NI, len(D3XS_COLS))
    okisor: np.ndarray = None                          # (YEARS.n, 3, NI, 5)
    okiso2x: np.ndarray = None                         # (YEARS.n, NX, 3, 4, 7)
    kfprx: np.ndarray = None                           # (YEARS.n, NX, 4, NI, 3)  stat が作る


def new_agg():
    ag = Agg()
    ag.ks = {n: np.zeros((YEARS.n, 4)) for n in _A_NAMES}
    ag.gee = np.zeros((YEARS.n, 4, NX, 71)); ag.geept = np.zeros((YEARS.n, 4, NX, 71))
    ag.d3x = np.zeros((YEARS.n, NX, 4, NI, len(D3X_COLS)))
    ag.d3xs = np.zeros((YEARS.n, NX, 4, NI, len(D3XS_COLS)))
    ag.okisor = np.zeros((YEARS.n, 3, NI, 5))
    ag.okiso2x = np.zeros((YEARS.n, NX, 3, 4, 7))
    ag.kfprx = np.zeros((YEARS.n, NX, 4, NI, 3))
    return ag


# ================================================================ 被保険者

def shkehiho(ctx, st, ag, k):
    """被保険者数と標準報酬総額。港: emp_kyufu/shkehiho.py:shkehiho"""
    s, xend, K = ctx.s, ctx.xend, ctx.K
    kou2 = ctx.kou2
    A = ag.ks
    x = np.arange(15, 86)
    g = st.g[15:86, 0:71]; gpt = st.gpt[15:86, 0:71]; bb = st.bb[15:86, 0:71]
    ag.gee[k, s, 15:86, :] = g
    ag.geept[k, s, 15:86, :] = gpt
    gs = g.sum(1); gps = gpt.sum(1)

    def add(name, val, dum=True):
        A[name][k, s] += val
        if dum:
            A[name + "dum"][k, s] += val

    add("ap", gs.sum())
    add("ap65", gs[(x >= 65) & (x <= 69)].sum())
    if xend > 70:
        add("ap70", gs[x >= 70].sum())
    if xend > 75:
        add("ap75", gs[x >= 75].sum())
    if xend > 85:
        add("ap85", gs[x >= 85].sum())
    if kou2:
        add("appart", gps.sum())
        add("appart65", gps[(x >= 65) & (x <= 69)].sum())
        if xend > 70:
            add("appart70", gps[x >= 70].sum())
        if xend > 75:
            add("appart75", gps[x >= 75].sum())
        if xend > 85:
            add("appart85", gps[x >= 85].sum())
    iku = K.ikucoe[k, 15:86]
    gb = (g * bb).sum(1)
    young = (x >= 20) & (x <= 49)
    tmp = np.where(young, gb * (1. - iku), np.where((ctx.flg_hiho70 == 0) & (x < ctx.hihonen), gb, 0.))
    tmr = np.where(young, gb * iku, 0.)
    add("a", tmp.sum())
    add("aiku", tmr[x < 65].sum())
    add("a60", tmp[x >= 60].sum())
    add("a65", tmp[x >= 65].sum())
    if xend > 70:
        add("a70", tmp[x >= 70].sum())
    if xend > 75:
        add("a75", tmp[x >= 75].sum())
    if xend > 85:
        add("a85", tmp[x >= 85].sum())
    # 適用拡大の按分（2024年10月）
    if kou2 and k in (ctx.partyr3 - 1, ctx.partyr3):
        tmq = ctx.hs.dmpt2[k, 15:86, s] * ctx.E.ad[k]
        lp = ctx.lpt1[k, s, 15:86]
        tp = np.where(young, lp * tmq * (1. - iku), lp * tmq)
        tr = np.where(young, lp * tmq * iku, 0.)
        A["apart"][k, s] += tp.sum(); A["aikupart"][k, s] += tr.sum()
        for a0, nm in ((60, "a60part"), (65, "a65part"), (70, "a70part"), (75, "a75part"), (85, "a85part")):
            A[nm][k, s] += tp[x >= a0].sum()
        if k == ctx.partyr3:
            A["adum"][k, s] -= tp.sum(); A["aikudum"][k, s] -= tr.sum()
            for a0, nm in ((60, "a60dum"), (65, "a65dum"), (70, "a70dum"), (75, "a75dum"), (85, "a85dum")):
                A[nm][k, s] -= tp[x >= a0].sum()
    # 適用拡大（レバー）の按分（オプションの年度）
    if kou2 and ctx.flg_part >= 1 and k in (ctx.partyr4 - 1, ctx.partyr4):
        tmq = ctx.hs.dmpt2[k, 15:86, s] * ctx.E.ad[k]
        lp = ctx.lpt2[k, s, 15:86] + ctx.lpt3[k, s, 15:86] + ctx.lpt4[k, s, 15:86]
        tp = np.where(young, lp * tmq * (1. - iku), lp * tmq)
        tr = np.where(young, lp * tmq * iku, 0.)
        A["apart"][k, s] += tp.sum(); A["aikupart"][k, s] += tr.sum()
        for a0, nm in ((60, "a60part"), (65, "a65part"), (70, "a70part"), (75, "a75part"), (85, "a85part")):
            A[nm][k, s] += tp[x >= a0].sum()
        if k == ctx.partyr4:
            A["adum"][k, s] -= tp.sum(); A["aikudum"][k, s] -= tr.sum()
            for a0, nm in ((60, "a60dum"), (65, "a65dum"), (70, "a70dum"), (75, "a75dum"), (85, "a85dum")):
                A[nm][k, s] -= tp[x >= a0].sum()


# ================================================================ 受給権者

_JS_H = (1, 3, 4, 5, 6, 14, 23)
_N_OF = {1: 2, 14: 3}


def shkejken(ctx, st, k):
    """受給権者の人数と 1 人あたり年金額 (t4k, hn2k, t6k)。港: emp_kyufu/shkejken.py:shkejken"""
    s, pseid, KIJ = ctx.s, ctx.pseid, ctx.KIJ
    sd, K, ku, E = ctx.sd, ctx.K, ctx.ku, ctx.E
    SH = ctx.C["shke"]
    x = np.arange(NX); xx = np.arange(NXX)
    year = YEARS.label(k)
    coh = year - x
    xxr4 = np.maximum(60, ctx.sk.xxr(coh)); xrb4 = np.maximum(60, ctx.sk.xrb(coh))
    xxr_stale = int(max(60, ctx.sk.xxr(year - int(SH["e26_stale_xxr_age"]))))       # E26
    valid = (x <= 114)
    t4k = np.zeros((NX, NXX, NI)); hn2k = np.zeros((NX, NXX, NI, 3)); t6k = np.zeros((NX, NXX, NI, NJ))
    hantei = (ctx.flg_hantei == 0 and k >= KIJ + 1 and pseid == 0 and s <= 2)
    HC = SH["hantei_cohorts"]
    hk = (coh >= HC["from"]) & (coh <= HC["to"])
    hk |= np.isin(coh, HC["extra_male"] if s == 1 else HC["extra_female"])
    rh = st.rhantei; fh = st.fhantei
    routsu = ctx.routsu
    rc = K.rc[k]
    kd = K.kd[k]
    ratio32 = sd.adt[3] / sd.adt[2]
    KU = ctx.pol.get("kounen.kuriage.new_rate")
    jj = ((k >= YEARS.i(KU["year"])) & (coh >= KU["cohort"])).astype(int)
    tmp1 = np.zeros(NX); tmp2 = np.zeros((NX, NJ)); ok4_t4 = None; ok4_t6 = None
    nsx = _rnd(K.ns[k]).astype(int)
    sp_coh = year - nsx
    for i in range(1, NI):
        nxx = NXX if i <= 4 else 1
        XX = xx[:nxx]
        A65 = 65 - XX
        if i <= 4:
            xxr, xrb = xxr4, xrb4
        else:
            xxr, xrb = np.full(NX, xxr_stale), np.zeros(NX, dtype=int)
        lt65 = x[:, None] < A65[None, :]                     # x < 65 − xx
        late = (XX > 5)[None, :] & (x[:, None] < 60 + XX[None, :])
        skip_jken = ((xrb > 60)[:, None] & lt65 & (x < xrb)[:, None] & (XX <= 5)[None, :]) | late
        ok = ~skip_jken & valid[:, None]
        t4 = np.where(ok, st.r[:, :nxx, i], 0.)
        h2 = np.where(ok[..., None], st.hn[:, :nxx, i, 1:3], 0.)
        if hantei and i <= 4:
            r0 = st.r[:, 0, :]
            o0 = ok[:, 0]
            if i == 1:
                t4[:, 0] = np.where(o0 & ~hk, r0[:, 1] - (rh[:, 0, 2] + rh[:, 0, 3] + rh[:, 0, 4]), t4[:, 0])
            elif i == 2:
                t4[:, 0] = np.where(o0, r0[:, 2] + rh[:, 0, 2], t4[:, 0])
            elif i == 3:
                t4[:, 0] = np.where(o0 & ~hk, np.maximum(r0[:, 3] + rh[:, 0, 3], r0[:, 3] * routsu[s, 3, 1]), t4[:, 0])
            else:
                new = np.maximum(r0[:, 4] + rh[:, 0, 4], r0[:, 4] * routsu[s, 4, 1])
                t4[:, 0] = np.where(o0, new, t4[:, 0])
                tmp1 = -rh[:, 0, 4] - (r0[:, 4] - new)
                ok4_t4 = o0
        if i == 1:
            sen = (x >= 60) & (x <= 69) & (xxr > 60)
            t4[:, 0] += np.where(sen, st.rsen, 0.)
            h2[:, 0, 0] += np.where(sen, st.hnsen[:, 1], 0.); h2[:, 0, 1] += np.where(sen, st.hnsen[:, 2], 0.)
        # ---- 年金額: 本来水準・従前額保障・8割下限の高い方 ----
        skip_j = ((i <= 8) & (x >= 60)[:, None] & (xrb > 60)[:, None] & lt65 & (x < xrb)[:, None] & (XX <= 5)[None, :]) | late
        okj = ~skip_j & valid[:, None]
        F = st.f[:, :nxx, i]; Fm = st.f_min[:, :nxx, i]; Fh = st.f_hik[:, :nxx, i]
        T = np.maximum(F, Fm)
        T[..., 1] = np.maximum(T[..., 1], Fh[..., 1]); T[..., 10] = np.maximum(T[..., 10], Fh[..., 10])
        T[..., 13] = 0.; T[..., 22] = 0.; T[..., 0] = 0.
        t6 = np.where(okj[..., None], T, 0.)
        if hantei and i <= 4:
            o0 = okj[:, 0]
            for j in _JS_H:
                n = _N_OF.get(j, 1)
                cur = t6[:, 0, j]
                if i == 1:
                    new = np.where(~hk, cur - (fh[:, 0, 2, j] + fh[:, 0, 3, j] + fh[:, 0, 4, j]), cur)
                elif i == 2:
                    new = cur + fh[:, 0, 2, j]
                elif i == 3:
                    new = np.where(~hk, np.maximum(cur + fh[:, 0, 3, j], cur * routsu[s, 3, n]), cur)
                else:
                    new = np.maximum(cur + fh[:, 0, 4, j], cur * routsu[s, 4, n])
                    tmp2[:, j] = -fh[:, 0, 4, j] - (cur - new)
                    ok4_t6 = o0
                t6[:, 0, j] = np.where(o0, new, cur)
        # ---- 遺族の有子・無子 ----
        if i in (11, 12):
            m = (x >= 19)[:, None]
            rck = rc[:, None]
            if s != 2:
                for j in (14, 17):
                    t6[..., j] = np.where(m, t6[..., j] * rck, t6[..., j])
                for j in (7, 8, 18):
                    t6[..., j] = np.where(m, t6[..., j] * (1. - rck), t6[..., j])
            else:
                t6[..., 14] = np.where(m, t6[..., 14] * rck, t6[..., 14])
                for j in (17, 18, 20):
                    t6[..., j] = np.where(m, 0., t6[..., j])
        if i == 13 and s == 2:
            t6[..., 17] = np.where((x >= 19)[:, None], 0., t6[..., 17])
        # ---- 繰上げ減額・繰下げ増額 ----
        if i <= 4:
            jj2 = jj[:, None]
            rigbe = ku.rigbe[s, A65[None, :], xrb[:, None], jj2]
            rigd = ku.rigd[s, A65[None, :], xxr[:, None], jj2]
            rigk = ku.rigk[s, A65[None, :], xxr[:, None], jj2]
            early = (XX <= 5)[None, :]
            m1 = (x >= 60)[:, None] & (xrb > 60)[:, None] & early & (A65[None, :] < xrb[:, None])
            t6[..., 1] = np.where(m1, t6[..., 1] * rigbe, t6[..., 1])
            c = (xrb > 60)[:, None] & (A65[None, :] < xrb[:, None])
            t3 = np.where(c, np.where(lt65, 0., t6[..., 3] * rigk), np.where((x < 65)[:, None], 0., t6[..., 3]))
            t6[..., 3] = np.where(early, t3, t6[..., 3])
            z2 = lt65 & (x < xxr)[:, None] & (xxr > 60)[:, None]
            t2 = np.where(lt65, np.where(z2, 0., t6[..., 2]), np.where((x < 65)[:, None], t6[..., 2] * rigd, 0.))
            t14 = np.where(lt65, 0., np.where((x < 65)[:, None], t6[..., 14] * rigk, t6[..., 14] * (rigd + rigk)))
            t6[..., 2] = np.where(early, t2, t6[..., 2]); t6[..., 14] = np.where(early, t14, t6[..., 14])
            lateok = (XX > 5)[None, :] & ~late
            tmgbe = (1. + ctx.C["kurisage_zogaku"] * (XX - 5) * 12.)[None, :]
            for j in (1, 3, 14):
                t6[..., j] = np.where(late, 0., np.where(lateok, t6[..., j] * tmgbe, t6[..., j]))
            t6[..., 2] = np.where(late | lateok, 0., t6[..., 2])
        # ---- 加給・振替加算の対象者割合 ----
        if i <= 8:
            ii = 1 if i <= 2 else (6 if i <= 4 else 2)
            t6[..., 4] *= kd[ii, 1][:, None]; t6[..., 5] *= (kd[ii, 2] + kd[ii, 3] * ratio32)[:, None]
            t6[..., 6] *= kd[ii, 4][:, None]; t6[..., 19] *= kd[ii, 1][:, None]; t6[..., 23] *= kd[ii, 1][:, None]
            z = (x < xxr)[:, None] | late
            for j in (4, 5, 6, 19, 23):
                t6[..., j] = np.where(z, 0., t6[..., j])
        elif i <= 10:
            ii = 3 if i == 9 else 4
            t6[..., 4] *= kd[ii, 1][:, None]; t6[..., 5] *= (kd[ii, 2] + kd[ii, 3] * ratio32)[:, None]
            t6[..., 6] *= kd[ii, 4][:, None]; t6[..., 19] *= kd[ii, 1][:, None]
            t6[..., 20] *= (kd[ii, 2] + kd[ii, 3] * ratio32)[:, None]; t6[..., 21] *= (kd[ii, 2] + kd[ii, 3] * ratio32)[:, None]
        else:
            f5 = (kd[5, 2] + kd[5, 3] * ratio32)[:, None]
            t6[..., 5] *= f5; t6[..., 20] *= f5; t6[..., 21] *= f5
        # ---- 長期加入者の特例の年金額 ----
        if i == 1:
            fs = np.maximum(st.fsen, st.fsenmin)
            fs[:, 1] = np.maximum(np.maximum(st.fsen[:, 1], st.fsenhik[:, 1]), st.fsenmin[:, 1])
            fs[:, 10] = np.maximum(np.maximum(st.fsen[:, 10], st.fsenhik[:, 10]), st.fsenmin[:, 10])
            t6[:, 0, 1] += np.where(sen, fs[:, 1], 0.); t6[:, 0, 2] += np.where(sen, fs[:, 2], 0.)
            t6[:, 0, 4] += np.where(sen, fs[:, 4] * kd[1, 1], 0.)
            t6[:, 0, 5] += np.where(sen, fs[:, 5] * (kd[1, 2] + kd[1, 3] * ratio32), 0.)
            t6[:, 0, 23] += np.where(sen, fs[:, 23] * kd[1, 1], 0.)
        t6[..., 7] = np.where(((x >= 65) | (x < 40))[:, None], 0., t6[..., 7])
        for j in (8, 15, 16):
            t6[..., j] = np.where((x < 65)[:, None], 0., t6[..., j])
        if i == 12:
            t6[..., 12] = np.maximum(0., t6[..., 12] - t6[..., 10] - t6[..., 5] - t6[..., 9] - t6[..., 11])
        else:
            t6[..., 12] = np.maximum(0., t6[..., 12] - t6[..., 10] - t6[..., 11])
        m15 = x >= 15
        z6 = m15 & ((nsx < 65) | (sp_coh < SH["furikae_spouse_cohort_from"]))
        z18 = m15 & (sp_coh >= SH["furikae_spouse_cohort_from"])
        t6[..., 6] = np.where(z6[:, None], 0., t6[..., 6]); t6[..., 18] = np.where(z18[:, None], 0., t6[..., 18])
        if pseid == 0 and s <= 2 and k >= ctx.partyr3 and i <= 4:
            m = ((x >= 60) & (x <= 70))[:, None]
            col = 1 if i <= 2 else 2
            sign = -1. if i in (1, 3) else 1.
            t6[..., 1] = np.where(m, t6[..., 1] + sign * st.fpart[:, :nxx, col], t6[..., 1])
        t4k[:, :nxx, i] = t4; hn2k[:, :nxx, i, 1:3] = h2; t6k[:, :nxx, i] = t6
    if hantei:                                               # i = 4 が i = 1 / 2 を直す（港の順）
        t4k[:, 0, 2] = np.where(ok4_t4 & hk, t4k[:, 0, 2] - tmp1, t4k[:, 0, 2])
        t4k[:, 0, 1] = np.where(ok4_t4 & ~hk, t4k[:, 0, 1] - tmp1, t4k[:, 0, 1])
        for j in _JS_H:
            t6k[:, 0, 2, j] = np.where(ok4_t6 & hk, t6k[:, 0, 2, j] - tmp2[:, j], t6k[:, 0, 2, j])
            t6k[:, 0, 1, j] = np.where(ok4_t6 & ~hk, t6k[:, 0, 1, j] - tmp2[:, j], t6k[:, 0, 1, j])
    return t4k, hn2k, t6k


# ================================================================ 受給者

def _siku(ctx, k, i):
    """給付 i の支給率 (gv, gvr, gvk, gvkk)（年齢の配列）。港: emp_kyufu/siku.py:siku"""
    s3 = 2 if ctx.s == 2 else 1
    S = ctx.sik[k, :, s3]                                     # (NX, 20, 3)
    x = np.arange(NX)
    one = np.ones(NX); zero = np.zeros(NX)
    hi = x >= max(ctx.xend, 85)
    # 高在老の撤廃（レバー kozax）: 在職（i 偶数）を kozaxyr 年度から kozax 歳以上で退職扱いの率に
    kz = (x >= ctx.kozax) if (ctx.flg_kozax and k >= ctx.kozaxyr) else np.zeros(NX, dtype=bool)
    if i in (1, 3):
        gv, gvr, gvk = S[:, i, 1], S[:, i, 2], S[:, 14 if i == 1 else 15, 1]; gvkk = gv
    elif i in (2, 4):
        gv = np.where(kz, S[:, i - 1, 1], S[:, i, 1]); gvr = np.where(kz, S[:, i - 1, 2], S[:, i, 2])
        gvk = S[:, 14 if i == 2 else 15, 1]; gvkk = zero
    elif i in (5, 7):
        gv, gvr = S[:, i, 1], S[:, i, 2]; gvk = gvr; gvkk = gv
    elif i in (6, 8):
        sel = hi | kz
        gv = np.where(sel, S[:, i - 1, 1], S[:, i, 1]); gvr = np.where(sel, S[:, i - 1, 2], S[:, i, 2])
        gvk = gvr; gvkk = np.where(hi, gv, 0.)
    elif i in (9, 10):
        gv, gvr, gvk = S[:, i, 1], S[:, i, 2], S[:, 16, 1]; gvkk = S[:, 18, 1] if i == 10 else one
    else:
        gv, gvr, gvk = S[:, i, 1], S[:, i, 2], S[:, 17, 1]; gvkk = one
    return gv, gvr, gvk, gvkk


def jikoutou_rates(pol, system, flg_hantei=0):
    """事故等の補正率 tmsii[i]（厚年は加算、共済は倍率）。港: emp_kyufu/shkejsha.py:shkejsha"""
    J = pol.get("kounen.jikoutou")
    t = np.zeros(NI) if system == "kou" else np.ones(NI)
    t[0] = 0.
    if flg_hantei != 0:
        return t
    for i, v in J[system].items():
        t[int(i)] = v
    if system == "kou":
        t[2] = t[3] = t[4] = t[1]; t[6] = t[5]; t[8] = t[7]
    return t


def shkejsha(ctx, st, k, t4k, hn2k, t6k):
    """支給率を掛けて受給者に (t4, hn2, t6)。`t4k` `t6k` も裁定遅れ等で書き換える。
    港: emp_kyufu/shkejsha.py:shkejsha"""
    s, pseid, KIJ = ctx.s, ctx.pseid, ctx.KIJ
    x = np.arange(NX)
    t4 = np.zeros_like(t4k); hn2 = np.zeros_like(hn2k); t6 = np.zeros_like(t6k)
    tmsii = jikoutou_rates(ctx.pol, ctx.system, ctx.flg_hantei)
    JF = ctx.pol.get("kounen.jikoutou.fade")
    kf, kz = YEARS.i(JF["full_until"]), YEARS.i(JF["zero_from"])
    ss = 1 if s == 3 else s
    nos_on = (k <= KIJ + 5)
    m60 = (x >= 60) & (x <= 69)
    for i in range(1, NI):
        gv, gvr, gvk, gvkk = _siku(ctx, k, i)
        t4[:, :, i] = t4k[:, :, i] * gvr[:, None]
        hn2[:, :, i] = hn2k[:, :, i] * gvr[:, None, None]
        mult = np.repeat(gv[:, None], NJ, axis=1)
        for j in (6, 14, 21):
            mult[:, j] = gvk
        if i == 10:
            for j in (17, 19, 20):
                mult[:, j] = gvkk
        t6[:, :, i] = t6k[:, :, i] * mult[:, None, :]
        js = [j for j in range(1, NJ) if (j <= 12 and j != 6) or j == 23]
        if pseid == 0:
            if k <= kf:
                fac = 1. + tmsii[i]
            elif k < kz:
                fac = 1. + tmsii[i] * (kz - k) / float(kz - kf)
            else:
                fac = 1.
            t6[:, :, i, js] *= fac
        elif i >= 5 and i not in (9, 11):
            jk = [1, 2, 3, 7, 8, 9, 10, 11, 12]
            t6[:, :, i, jk] *= tmsii[i]; t6k[:, :, i, jk] *= tmsii[i]
        if nos_on and i <= 4:
            n2 = np.where(m60, ctx.nos[k, np.minimum(x, 69), ss, i, 2], 1.)
            n1 = np.where(m60, ctx.nos[k, np.minimum(x, 69), ss, i, 1], 1.)
            t4k[:, :, i] *= n2[:, None]
            t6k[:, :, i, 1:] *= n1[:, None, None]
        if i == 11 and s != 2:
            m = (x >= 19) & (1. - ctx.K.rc[k] >= _EPS)
            den = np.where(m, 1. - ctx.K.rc[KIJ], 1.)
            t6k[:, :, i, 7] /= den[:, None]; t6k[:, :, i, 8] /= den[:, None]
    return t4, hn2, t6


# ================================================================ 給付費の表

def shkejuk(ctx, ag, k, t4k, hn2k, t6k, t4, hn2, t6):
    """`d3x`（受給者）と `d3xs`（受給権者）の列へ足す。港: emp_kyufu/shkejuk.py:shkejuk"""
    s = ctx.s
    x = np.arange(NX)
    abfac = float(ctx.C["shke"]["ab_factor"][ctx.system])
    kk0 = ctx.sd.ee[1] if s != 3 else ctx.sd.ee[2]
    for jj, (P4, P6, H) in ((1, (t4k, t6k, hn2k)), (2, (t4, t6, hn2))):
        for i in range(1, NI):
            tmp = P6[:, :, i]                                 # (x, xx, j)
            n0 = P4[:, :, i]
            aba = H[:, :, i, 1]; abb = H[:, :, i, 1] + H[:, :, i, 2]
            with np.errstate(divide="ignore", invalid="ignore"):
                ab = np.where((abb > _EPS) & (aba >= _EPS), aba / np.where(abb > _EPS, abb, 1.), 0.) * abfac
            kk = np.full(NX, kk0)
            if i in (2, 4, 6, 8):
                kk[x < 65] = 0.
            kk = kk[:, None]
            tmx1 = tmp[..., 1] + tmp[..., 10]
            tmy1 = tmp[..., 18] if i == 11 else 0.
            tmx2 = tmp[..., 2] + tmp[..., 11]
            tmy2 = tmp[..., 15] + tmp[..., 16] * 3. / 4. + tmp[..., 17] + (0. if i == 11 else tmp[..., 18])
            tmy2b = tmp[..., 17] + (0. if i == 11 else tmp[..., 18])
            tmz = tmp[..., 14] if i <= 4 else 0.
            tmx4 = tmp[..., 4] + tmp[..., 5] + tmp[..., 23]; tmy4 = tmp[..., 19] + tmp[..., 20]
            t789 = tmp[..., 7] + tmp[..., 8] + tmp[..., 9]
            cols = {
                0: n0, 7: tmx1 - tmy1, 8: tmx2 - tmy2, 9: tmp[..., 3], 10: tmx4 - tmy4, 11: t789, 12: tmp[..., 12],
                13: (tmx1 - tmy1) * ab, 14: (tmx2 - tmy2b + tmz) * ab, 15: tmp[..., 3] * ab, 16: (tmx4 - tmy4) * ab,
                17: t789 * ab, 18: tmp[..., 12] * ab,
                22: tmp[..., 15] + tmp[..., 16] * 3. / 4. + tmp[..., 17], 23: tmy4, 24: tmp[..., 18], 25: tmp[..., 16] / 4.,
            }
            if jj == 2:
                for j, v in cols.items():
                    ag.d3x[k, :, s, i, _C[j]] += np.asarray(v).sum(-1) if np.ndim(v) else 0.
            else:
                for j in D3XS_COLS:
                    ag.d3xs[k, :, s, i, _CS[j]] += cols[j].sum(-1)


# ================================================================ ④へ渡す数

def shkekiso(ctx, ag, k, t4k, t6k, t4, t6):
    """基礎年金の受給者数 `okisor` と給付費 `okiso2x`。港: emp_kyufu/shkekiso.py:shkekiso"""
    s = ctx.s
    x = np.arange(NX); xx = np.arange(NXX)
    cl, cl2, rc = ctx.K.cl[k], ctx.K.cl2[k], ctx.K.rc[k]
    same = 2 if s == 2 else 1
    for i in range(1, NI):
        ss = same if i <= 10 else (1 if s == 2 else 2)
        if i in (9, 11):
            _, _, gvk, _ = _siku(ctx, k, i)
            base = t4k[:, :, i] * gvk[:, None]
        elif i == 10:
            _, _, _, gvkk = _siku(ctx, k, i)
            base = t4k[:, :, i] * gvkk[:, None]
        else:
            base = t4[:, :, i]
        base = np.where(base <= 1.0e-30, 0., base)
        v1 = np.where((x < 65)[:, None], 0., base)
        v2 = base.copy()
        if i <= 4:
            v2 = np.where(x[:, None] < (65 - xx)[None, :], 0., v2)
        elif i <= 8:
            v2 = np.where((x < 65)[:, None], 0., v2)
        elif i == 9:
            v2 = v2 * (cl[1] + cl[2])
        elif i == 10:
            v2 = v2 * (cl2[1] + cl2[2])
        else:
            v2 = np.where((x >= 19)[:, None], v2 * rc[:, None], v2)
        ag.okisor[k, ss, i, 1] += v1.sum()
        ag.okisor[k, ss, i, 2] += v2.sum()
        ag.okisor[k, ss, i, 3] += np.where((x >= 65)[:, None], 0., v2).sum()
        ag.okisor[k, ss, i, 4] += np.where((x < 65)[:, None], 0., v2).sum()
        T = t6[:, :, i]
        O = ag.okiso2x[k, :, ss]
        if i <= 4:
            O[:, 1, 1] += T[..., 14].sum(1); O[:, 1, 3] += T[..., 6].sum(1); O[:, 1, 5] += T[..., 19].sum(1)
        else:
            T0 = T[:, 0]
            if i <= 8:
                O[:, 1, 4] += T0[:, 15]; O[:, 1, 5] += T0[:, 19]; O[:, 1, 6] += T0[:, 16] * 3. / 4.
            elif i == 9:
                O[:, 2, 1] += T0[:, 14]; O[:, 2, 2] += T0[:, 21]; O[:, 2, 3] += T0[:, 6]; O[:, 2, 5] += T0[:, 19]
            elif i == 10:
                O[:, 2, 4] += T0[:, 17]; O[:, 2, 5] += T0[:, 19] + T0[:, 20]
            elif i == 11:
                O[:, 1, 5] += T0[:, 18]; O[:, 3, 1] += T0[:, 14]; O[:, 3, 2] += T0[:, 21]
            else:
                O[:, 1, 5] += T0[:, 18]; O[:, 3, 4] += T0[:, 17]; O[:, 3, 5] += T0[:, 20]
    ss = same
    for a, b in ((1, 2), (3, 4), (5, 6), (7, 8)):
        ag.okisor[k, ss, a, 1:5] += ag.okisor[k, ss, b, 1:5]
        ag.okisor[k, ss, b, 1:5] = 0.


def shke_sigonen(ctx, k, t6k):
    """基礎45年化（レバー sigo）の読み替え: 障害（i=9）・遺族（i=11）の基礎年金相当分（j = 2, 7, 11, 12, 14。
    繰上げ繰下げ無し xx=0）に「加入可能年数 ÷ 40」を掛ける。経過的な差額（j=12）だけ 2 乗。
    港: emp_kyufu/shke.py:shke"""
    base = float(ctx.pol.get("kounen.sigo.base_years"))
    r = ctx.kflcan[k, cohort_index(k, np.arange(NX))] / base                # (NX,)
    for i in (9, 11):
        for j in (2, 7, 11, 14):
            t6k[:, 0, i, j] *= r
        t6k[:, 0, i, 12] *= r ** 2


def shke(ctx, st, ag, k):
    """年度 k の集計（港の `shke()` 1 回ぶん）。港: emp_kyufu/shke.py:shke"""
    shkehiho(ctx, st, ag, k)
    t4k, hn2k, t6k = shkejken(ctx, st, k)
    if ctx.flg_sigo == 1:
        shke_sigonen(ctx, k, t6k)
    t4, hn2, t6 = shkejsha(ctx, st, k, t4k, hn2k, t6k)
    shkejuk(ctx, ag, k, t4k, hn2k, t6k, t4, hn2, t6)
    shkekiso(ctx, ag, k, t4k, t6k, t4, t6)
    return t4k, hn2k, t6k, t4, hn2, t6
