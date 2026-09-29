# -*- coding: utf-8 -*-
"""②の 1 年度ぶんの推計（移植版 `siml.cpp` と `simlg/simlbzw/dsitk/simlsaite/simlrhnf`）
=========================================================================================
年度 `k` の状態を前年度から作る。移植版は年齢 `x` ごとに関数を呼ぶが、高速版は
(年齢, 経過年) をまとめて処理する。前年度の値を読んで当年度に書く漸化式なので、
**前年度の配列の複製**を取ってから一斉に書けば、移植版の降順ループと同じ答えになる。

    simlg        被保険者を 1 歳進める（継続・新規・待期・脱退の内訳）
    simlbzw      標準報酬（`bb`）・加入期間の区分（`z` `ze`）・平均標準報酬額（`w` `we`）
    dsitk        裁定時の資格（`it`）・支給開始年齢・期間・報酬比例額（`bk`）
    saitesho     障害の新規裁定（i = 9）
    saiteizohiho 被保険者死亡の遺族（i = 11。配偶者の年齢 `yx` の整数部と小数部に振り分け）
    saiteizojuk  受給者死亡の遺族（老齢 1/2/5・通算 3/4/7・障害 9/10 から）
    saitezai     在職のまま裁定（i = 2/4）。65・70 歳と 66〜69 歳で在職受給者を裁定し直す
    saitetai     退職しての裁定（i = 1/3）。長期加入者の特例（44 年）は `*sen` へ
    simlrhnf     受給者を 1 歳進める（残存率 × 改定率 ＋ 新規裁定）
    fpart        パート適用拡大で老齢から在職へ移す
    hantei       足元の実績に合わせる判定補正（厚年の男女だけ）

港の癖で残すもの（`検証/原本の不具合.md`）: E29（共済は exp(−脱退力)）、E30（障害の等級
割合が 0 のとき。いまの入力では通らない経路なので高速版は 0 にする）、E31（`rhantei` の
i = 1 が `x == xrb` で代入されない）。

港: emp_kyufu/siml.py:siml
仕様: §4.3（被保険者）、§5.4〜5.6（裁定・受給者）
"""
import numpy as np

from ...axis import YEARS
from .context import cohort_index
from .inputs import NX, NT, NXX, NI, NJ

__all__ = ["siml", "simlg", "simlbzw", "dsitk", "saitesho", "saiteizohiho", "saiteizojuk",
           "saitezai", "saitetai", "simlrhnf", "fpart", "hantei"]

_KKU_JS = (4, 5, 9, 19, 20, 21, 23)          # 加給・振替加算（67 歳の改定率を使う）
_EPS = 1.0e-6


def _rnd(a):
    """C99 の round()（0 から遠い方へ）を配列に。"""
    a = np.asarray(a, dtype=float)
    return np.where(a >= 0., np.floor(a + 0.5), -np.floor(-a + 0.5))


# ================================================================ 被保険者

def simlg(ctx, st, k):
    """被保険者を 1 歳進める。港: emp_kyufu/simlg.py:simlg（x をまとめて処理）"""
    s, pseid, xend, tend = ctx.s, ctx.pseid, ctx.xend, ctx.tend
    KIJ = ctx.KIJ
    kou2 = ctx.kou2
    K, l, lpt, lpt1, pop = ctx.K, st.l, st.lpt, ctx.lpt1, ctx.pop
    u = K.u[k]                                   # (NX, 4)
    q1 = K.q[k, :, 1]
    rt = K.rt[k]
    g0, gpt0, ge0 = st.g.copy(), st.gpt.copy(), st.ge.copy()
    xhi = xend if pseid != 0 else min(xend, 69 + k - KIJ)
    xm = np.arange(15, xhi + 1)                  # simlg を通す年齢
    xrb = np.maximum(60, ctx.sk.xrb(YEARS.label(k) - xm))
    T = tend
    surv = (1. - u[xm, 0]) if pseid == 0 else np.exp(-u[xm, 0])
    gz = np.zeros((len(xm), NT)); gzpt = np.zeros((len(xm), NT))
    gz[:, 1:T - 1] = g0[xm - 1, 0:T - 2] * surv[:, None]
    gz[:, T - 1] = (g0[xm - 1, T - 2] + g0[xm - 1, T - 1]) * surv
    if kou2:
        gzpt[:, 1:T - 1] = gpt0[xm - 1, 0:T - 2] * (1. - u[xm, 0])[:, None]
        gzpt[:, T - 1] = (gpt0[xm - 1, T - 2] + gpt0[xm - 1, T - 1]) * (1. - u[xm, 0])
        gz -= gzpt
    gezz = np.zeros((len(xm), NT))
    gezz[:, 0:T] = ge0[xm - 1, 0:T] * (1. - q1[xm])[:, None]
    ye = np.zeros((len(xm), NT))
    ye[:, 0:T] = ge0[xm - 1, 0:T] - gezz[:, 0:T]
    tmp = gezz[:, 0:T].sum(1)
    tmq = gz[:, 1:T].sum(1)
    tmv = gzpt[:, 1:T].sum(1)
    lk = l[k, s, xm]
    over = lk < tmq
    sc = np.where(tmq > _EPS, lk / np.where(tmq > _EPS, tmq, 1.), 0.)
    gz[over, 1:T] *= sc[over, None]
    tmq = np.where(over, lk, tmq)
    opt_year = ctx.flg_part >= 1 and k == ctx.partyr4              # 適用拡大（レバー）の年度
    lopt = (ctx.lpt2[k, s, xm] + ctx.lpt3[k, s, xm] + ctx.lpt4[k, s, xm]) if opt_year else 0.
    if kou2:
        if k == ctx.partyr3:
            cap = lpt[k, s, xm] - lpt1[k, s, xm]
        elif opt_year:
            cap = lpt[k, s, xm] - lopt
        else:
            cap = lpt[k, s, xm]
        overp = cap < tmv
        scp = np.where(tmv > _EPS, cap / np.where(tmv > _EPS, tmv, 1.), 0.)
        gzpt[overp, 1:T] *= scp[overp, None]
        tmv = np.where(overp, cap, tmv)
    tmr1 = np.zeros(len(xm)); tmr2 = np.zeros(len(xm))
    if s <= 2:
        pk = pop[k, s, xm]
        room = tmp + tmq + tmv < pk
        with np.errstate(divide="ignore", invalid="ignore"):
            base = np.minimum(1., np.maximum(rt[xm], tmp / (pk - tmq - tmv)))
        base = np.where(room, base, 0.)
        tmr1 = np.where(room, base * (lk - tmq), np.maximum(0., lk - tmq))
        if pseid == 0:
            if k == ctx.partyr3:
                t2 = (base * (lpt[k, s, xm] - lpt1[k, s, xm] - tmv)
                      + rt[xm] * np.minimum(1., np.maximum(0., (xm - 25) / 40.)) * lpt1[k, s, xm])
            elif opt_year:
                t2 = (base * (lpt[k, s, xm] - lopt - tmv)
                      + rt[xm] * np.minimum(1., np.maximum(0., (xm - 25) / 40.)) * lopt)
            else:
                t2 = base * (lpt[k, s, xm] - tmv)
            tmr2 = np.where(room, t2, np.maximum(0., lpt[k, s, xm] - tmv))
    else:
        tmr1 = rt[xm] * np.maximum(0., lk - tmq)
    gn = np.zeros((len(xm), NT)); gnpt = np.zeros((len(xm), NT))
    ok = (xm <= xrb) & (tmp > _EPS)
    with np.errstate(divide="ignore", invalid="ignore"):
        if kou2:
            tot = tmr1 + tmr2
            big = tmp >= tot
            fn1 = np.where(big, tmr1 / tmp, np.where(tot > _EPS, tmr1 / tot, 0.))
            fn2 = np.where(big, tmr2 / tmp, np.where(tot > _EPS, tmr2 / tot, 0.))
            gn[:, 0:T] = gezz[:, 0:T] * np.where(ok, fn1, 0.)[:, None]
            gnpt[:, 0:T] = gezz[:, 0:T] * np.where(ok, fn2, 0.)[:, None]
        else:
            fn1 = np.where(tmp >= tmr1, tmr1 / tmp, 1.)
            gn[:, 0:T] = gezz[:, 0:T] * np.where(ok, fn1, 0.)[:, None]
    gez = np.maximum(0., gezz - gn - gnpt)
    gnn = lk - gn[:, 0] - (gz[:, 1:T] + gn[:, 1:T]).sum(1)
    small = np.abs(gnn) < _EPS
    l[k, s, xm[small]] -= gnn[small]
    gnn[small] = 0.
    if (gnn <= -_EPS).any():
        raise ValueError("simlg: gnn < 0 (s=%d k=%d)" % (s, k))
    g = np.zeros((len(xm), NT)); ge = np.zeros((len(xm), NT)); y = np.zeros((len(xm), NT, 4))
    u2 = u[xm, 2][:, None]; u3 = u[xm, 3][:, None]
    # t = 1..T−1（T−1 は 2 つの経過年を寄せる）
    g[:, 1:T] = gz[:, 1:T] + gn[:, 1:T]
    prev = np.zeros((len(xm), NT)); prevpt = np.zeros((len(xm), NT))
    prev[:, 1:T - 1] = g0[xm - 1, 0:T - 2]; prev[:, T - 1] = g0[xm - 1, T - 2] + g0[xm - 1, T - 1]
    prevpt[:, 1:T - 1] = gpt0[xm - 1, 0:T - 2]; prevpt[:, T - 1] = gpt0[xm - 1, T - 2] + gpt0[xm - 1, T - 1]
    if kou2:
        y0 = prev - prevpt - gz
        tm0 = prev - prevpt
    else:
        y0 = prev - gz
        tm0 = prev if pseid == 0 else (prev + gz) / 2.
    y2 = tm0 * u2; y3 = tm0 * u3; y1 = y0 - y2 - y3
    neg = (y1 < -1.0e-12)
    neg[:, 0] = False
    if neg.any():
        bad = neg & ((xm <= xrb)[:, None] | (y1 <= -1.0e-2))
        if bad.any():
            raise ValueError("simlg: y1 < 0 (s=%d k=%d)" % (s, k))
        tt = y2 + y3
        with np.errstate(divide="ignore", invalid="ignore"):
            y2n = np.where(tt > 1.0e-12, y0 * y2 / tt, 0.)
            y3n = np.where(tt > 1.0e-12, y0 * y3 / tt, 0.)
        y0 = np.where(neg, np.where(tt > 1.0e-12, y0, 0.), y0)
        y2 = np.where(neg, y2n, y2); y3 = np.where(neg, y3n, y3); y1 = np.where(neg, 0., y1)
    y[:, 1:T, 0] = y0[:, 1:T]; y[:, 1:T, 1] = y1[:, 1:T]; y[:, 1:T, 2] = y2[:, 1:T]; y[:, 1:T, 3] = y3[:, 1:T]
    ge[:, 1:T] = gez[:, 1:T] + y1[:, 1:T]
    g[:, 0] = gn[:, 0] + gnn
    ge[:, 0] = gez[:, 0]
    gpt = np.zeros((len(xm), NT)); ypt = np.zeros((len(xm), NT, 4))
    gnnpt = np.zeros(len(xm))
    if kou2:
        gnnpt = lpt[k, s, xm] - gnpt[:, 0] - (gzpt[:, 1:T] + gnpt[:, 1:T]).sum(1)
        small = np.abs(gnnpt) < _EPS
        lpt[k, s, xm[small]] -= gnnpt[small]
        gnnpt[small] = 0.
        if (gnnpt <= -_EPS).any():
            raise ValueError("simlg: gnnpt < 0 (s=%d k=%d)" % (s, k))
        gpt[:, 1:T] = gzpt[:, 1:T] + gnpt[:, 1:T]
        yp0 = prevpt - gzpt
        yp2 = prevpt * u2; yp3 = prevpt * u3; yp1 = yp0 - yp2 - yp3
        negp = yp1 < -1.0e-12
        negp[:, 0] = False
        if negp.any():
            bad = negp & ((xm <= xrb)[:, None] | (yp1 < -1.0e-2))
            if bad.any():
                raise ValueError("simlg: ypt1 < 0 (s=%d k=%d)" % (s, k))
            tt = yp2 + yp3
            with np.errstate(divide="ignore", invalid="ignore"):
                y2n = np.where(tt > 1.0e-12, yp0 * yp2 / tt, 0.)
                y3n = np.where(tt > 1.0e-12, yp0 * yp3 / tt, 0.)
            yp0 = np.where(negp, np.where(tt > 1.0e-12, yp0, 0.), yp0)
            yp2 = np.where(negp, y2n, yp2); yp3 = np.where(negp, y3n, yp3); yp1 = np.where(negp, 0., yp1)
        ypt[:, 1:T, 0] = yp0[:, 1:T]; ypt[:, 1:T, 1] = yp1[:, 1:T]; ypt[:, 1:T, 2] = yp2[:, 1:T]; ypt[:, 1:T, 3] = yp3[:, 1:T]
        gpt[:, 0] = gnpt[:, 0] + gnnpt
        g[:, 1:T] += gpt[:, 1:T]
        y[:, 1:T] += ypt[:, 1:T]
        ge[:, 1:T] += yp1[:, 1:T]
        gn[:, 1:T] += gnpt[:, 1:T]
        gz[:, 1:T] += gzpt[:, 1:T]
        g[:, 0] += gpt[:, 0]
        gn[:, 0] += gnpt[:, 0]
        gnn = gnn + gnnpt
    # 書き戻し（t ≥ T は触らない）
    st.gz[xm] = gz; st.gzpt[xm] = gzpt; st.gn[xm] = gn; st.gnpt[xm] = gnpt
    st.gez[xm] = gez; st.ye[xm] = ye; st.gnn[xm] = gnn; st.gnnpt[xm] = gnnpt
    st.g[xm, 0:T] = g[:, 0:T]; st.ge[xm, 0:T] = ge[:, 0:T]
    st.y[xm, 1:T] = y[:, 1:T]
    if kou2:
        st.gpt[xm, 0:T] = gpt[:, 0:T]
        st.ypt[xm, 1:T] = ypt[:, 1:T]
    # 実績から逆算した死亡率
    hi = xm >= 61
    xh = xm[hi]
    tmz = gz[hi, 0:T].sum(1)
    if pseid == 0 and s <= 2:
        den = l[k - 1, s, xh - 1] + lpt[k - 1, s, xh - 1]
    else:
        den = l[k - 1, s, xh - 1]
    with np.errstate(divide="ignore", invalid="ignore"):
        st.q2[k, xh] = np.where(den > _EPS, 1. - np.maximum(0., np.minimum(1., tmz / den)), 1.)
    if pseid == 0 and xhi < xend:
        xo = np.arange(xhi + 1, xend + 1)
        with np.errstate(divide="ignore", invalid="ignore"):
            st.q2[k, xo] = np.where(l[k - 1, s, xo - 1] > _EPS,
                                    1. - np.minimum(1., l[k, s, xo] / l[k - 1, s, xo - 1]), 1.)


# ================================================================ 標準報酬・期間・平均標準報酬額

def _cht_table(ctx, k, x):
    """再評価率 `cht[ii, x]`（4 通り）。港: emp_kyufu/simlbzw.py:simlbzw の ii ループ"""
    E, C = ctx.E, ctx.C
    KE = YEARS.n - 1
    kk = min(k, KE - 3)
    x = np.asarray(x)
    hh, ci = E.hh, E.ci
    base = E.dir[k] * (1. + E.ci0[kk + 1]) * (1. + E.ci0[kk + 2])
    c0 = np.where(x <= 64, base / (1. + hh[kk + 1]) / (1. + hh[kk + 2]) / (1. + hh[kk + 3]),
                  np.where(x == 65, base / (1. + hh[kk + 1]) / (1. + hh[kk + 2]) / (1. + ci[kk + 3]),
                           np.where(x == 66, base / (1. + hh[kk + 1]) / (1. + ci[kk + 2]) / (1. + ci[kk + 3]),
                                    base / (1. + ci[kk + 1]) / (1. + ci[kk + 2]) / (1. + ci[kk + 3]))))
    c1 = np.ones(x.shape)
    c2 = np.full(x.shape, E.jz_shk[k] * C["jz_base"][0] * C["jz_base"][1])
    for m in range(YEARS.i(C["cht_from"]), k + 1):
        c2 = c2 * (1. + E.ci2[m, np.maximum(x - k + m, 67)])
    c3 = np.full(x.shape, base / (1. + hh[kk + 1]) / (1. + hh[kk + 2]) / (1. + hh[kk + 3]))
    cht = np.stack([c0, c1, c2, c3])
    X = C["cht_extra"]
    ex = np.prod([float(v) for v in X["all"]])
    coh = YEARS.label(k) - x
    cht = cht * np.where(coh >= X["cohort"], ex * X["factor"], ex)
    return cht


def _houjou_factor(ctx, k):
    """標準報酬上限の見直し（レバー houjou）の倍率。施行年度は半分、以降は倍率そのもの。男・第3種は r1、女は r2。
    港: emp_kyufu/simlbzw.py:simlbzw"""
    if not ctx.houjou:
        return 1.
    r = ctx.houjou_r[0] if ctx.s in (1, 3) else ctx.houjou_r[1]
    if k == ctx.houjouyr:
        return 1. + (r - 1.) / 2.
    return r if k > ctx.houjouyr else 1.


def simlbzw(ctx, st, k):
    """標準報酬・期間の区分・平均標準報酬額。港: emp_kyufu/simlbzw.py:simlbzw, simlbzw0"""
    s, pseid, xend, tend = ctx.s, ctx.pseid, ctx.xend, ctx.tend
    kou2 = ctx.kou2
    E, hs, K = ctx.E, ctx.hs, ctx.K
    hihonen = ctx.hihonen
    T = tend
    xm = np.arange(15, xend + 1)
    n = len(xm)
    bn = hs.bn[k, xm, s]; bnpt = hs.bnpt[k, xm, s] if s <= 2 else np.zeros(n)
    ad = E.ad[k]; h1 = 1. + E.h[k]
    brr = np.zeros(n)
    with np.errstate(divide="ignore", invalid="ignore"):
        brr = hs.br[k, xm, s] / hs.br[k - 1, xm - 1, s]      # 0/0 は港と同じく nan
    g, gpt, gn, gnpt, gz, gzpt, gez, ge = (st.g[xm], st.gpt[xm], st.gn[xm], st.gnpt[xm], st.gz[xm],
                                           st.gzpt[xm], st.gez[xm], st.ge[xm])
    y1 = st.y[xm, :, 1]; ypt1 = st.ypt[xm, :, 1]
    bb_old, bbnp_old, bbpt_old = st.bb.copy(), st.bbnp.copy(), st.bbpt.copy()
    z_old, ze_old, w_old, we_old = st.z.copy(), st.ze.copy(), st.w.copy(), st.we.copy()
    is15 = (xm == 15)[:, None]
    isend = (xm == xend)[:, None]
    Ts = slice(1, T)
    # ---- 標準報酬 bb（t ≥ 1）----
    bb0 = np.zeros((n, NT)); bb0[:, Ts] = bb_old[xm - 1, 0:T - 1]
    if kou2:
        bbnp0 = np.zeros((n, NT)); bbnp0[:, Ts] = bbnp_old[xm - 1, 0:T - 1]
        bbpt0 = np.zeros((n, NT)); bbpt0[:, Ts] = bbpt_old[xm - 1, 0:T - 1]
    else:
        bbnp0 = bb0.copy(); bbpt0 = np.zeros((n, NT))
    bb = np.zeros((n, NT))
    bbnp = bbnp_old[xm].copy(); bbpt = bbpt_old[xm].copy()      # 共済・3号は bbnp を書かない（港のまま）
    with np.errstate(divide="ignore", invalid="ignore"):
        if kou2:
            gnp = g - gpt
            num = bn[:, None] * ad * (gn - gnpt) + bbnp0 * brr[:, None] * h1 * (gz - gzpt)
            bbnp[:, Ts] = np.where(gnp[:, Ts] > _EPS, np.where(is15, bn[:, None] * ad, num[:, Ts] / gnp[:, Ts]), 0.)
            nump = bnpt[:, None] * ad * gnpt + bbpt0 * h1 * gzpt
            bbpt[:, Ts] = np.where(gpt[:, Ts] > _EPS, np.where(is15, bnpt[:, None] * ad, nump[:, Ts] / gpt[:, Ts]), 0.)
            bbnp[:, Ts] = np.where(isend, bbnp0[:, Ts] * brr[:, None] * h1, bbnp[:, Ts])
            bbpt[:, Ts] = np.where(isend, bbpt0[:, Ts] * h1, bbpt[:, Ts])
            bb[:, Ts] = np.where(g[:, Ts] > _EPS, (bbnp[:, Ts] * gnp[:, Ts] + bbpt[:, Ts] * gpt[:, Ts]) / g[:, Ts], 0.)
        else:
            num = bn[:, None] * ad * gn + bb0 * brr[:, None] * h1 * gz
            bb[:, Ts] = np.where(g[:, Ts] > _EPS, np.where(is15, bn[:, None] * ad, num[:, Ts] / g[:, Ts]), 0.)
            bb[:, Ts] = np.where(isend, bb0[:, Ts] * brr[:, None] * h1, bb[:, Ts])
        # ---- t = 0 ----
        g00 = g[:, 0] > _EPS
        if kou2:
            bb[:, 0] = np.where(g00, (bn * (g[:, 0] - gpt[:, 0]) + bnpt * gpt[:, 0]) * ad / np.where(g00, g[:, 0], 1.), 0.)
            bbnp[:, 0] = np.where(g00, bn * ad, bbnp_old[xm, 0])           # g が 0 なら前年度のまま
            bbpt[:, 0] = np.where(g00, bnpt * ad, 0.)
        else:
            bb[:, 0] = np.where(g00, bn * ad, 0.)
            bbpt[:, 0] = np.where(g00, bbpt[:, 0], 0.)
        bb[:, 0] = np.where(xm == xend, bn * ad, bb[:, 0])
        if s <= 2:
            bbpt[:, 0] = np.where(xm == xend, bnpt * ad, bbpt[:, 0])
    # 70 歳以上の報酬は 0（厚年）。局所の bbnp0/bbpt0/bb0 は 71 歳以上で 0
    if pseid == 0:
        hi = (xm >= hihonen)[:, None]
        bb[:, Ts] = np.where(hi, 0., bb[:, Ts])
        if kou2:
            bbnp[:, Ts] = np.where(hi, 0., bbnp[:, Ts]); bbpt[:, Ts] = np.where(hi, 0., bbpt[:, Ts])
        hi1 = (xm >= hihonen + 1)[:, None]
        bbnp0 = np.where(hi1, 0., bbnp0); bbpt0 = np.where(hi1, 0., bbpt0); bb0 = np.where(hi1, 0., bb0)
    st.bb[xm, 0:T] = bb[:, 0:T]; st.bbnp[xm, 0:T] = bbnp[:, 0:T]; st.bbpt[xm, 0:T] = bbpt[:, 0:T]
    # ---- 加入期間の区分 z / ze ----
    coh = YEARS.label(k) - xm
    dx = 60
    if ctx.flg_sigo >= 1:                                    # 45年化: 区分の境を 20 + 加入可能年数 に（生年度ごと）
        dx = 20 + np.maximum(np.round(ctx.sd.can[cohort_index(k, xm)]), 40).astype(int)
    A = np.zeros((n, 7), dtype=bool)          # (x, j) 半年の補正が要る区分
    B = np.zeros((n, 7), dtype=bool)          # 境の年齢（半分だけ）
    Cc = np.zeros((n, 7), dtype=bool)         # 脱退側を 0 にする境
    for j in range(7):
        cond = (j == 0) | (j == 4)
        cond = cond | ((s == 1) & (xm >= 40) & (j == 5)) | ((s >= 2) & (xm >= 35) & (j == 5)) | ((xm >= 20) & (xm <= dx) & (j == 6))
        A[:, j] = (xm <= hihonen) & cond
        B[:, j] = ((s == 1) & (xm == 40) & (j == 5)) | ((s >= 2) & (xm == 35) & (j == 5)) | (((xm == 20) | (xm == dx)) & (j == 6)) | (xm == hihonen)
        Cc[:, j] = ((s == 1) & (xm == 40) & (j == 5)) | ((s >= 2) & (xm == 35) & (j == 5)) | ((xm == 20) & (j == 6))
    z = np.zeros((n, NT, 2, 7)); ze = np.zeros((n, NT, 2, 7))
    for i in (0, 1):
        z0 = np.zeros((n, NT, 7)); ze0 = np.zeros((n, NT, 7))
        z0[:, Ts] = z_old[xm - 1, 0:T - 1, i, :7]
        z0[:, T - 1] = np.where(z0[:, T - 1] <= _EPS, z_old[xm - 1, T - 1, i, :7], z0[:, T - 1])
        ze0[:, 0:T] = ze_old[xm - 1, 0:T, i, :7]
        tm1 = gn[:, :, None] * ze0 + gz[:, :, None] * z0
        tm2 = gez[:, :, None] * ze0 + y1[:, :, None] * z0
        if i == 0 or s == 3:
            half = np.where(B[:, None, :], gz[:, :, None] / 2. + gn[:, :, None] / 2., gz[:, :, None] + gn[:, :, None] / 2.)
            tm1 = tm1 + np.where(A[:, None, :], half, 0.)
            tm2 = tm2 + np.where(A[:, None, :], np.where(Cc[:, None, :], 0., y1[:, :, None] / 2.), 0.)
            tm1[:, 0] = gn[:, 0, None] * ze0[:, 0] + np.where(A, (st.gnn[xm] + gn[:, 0])[:, None] / 2., 0.)
        else:
            tm1[:, 0] = gn[:, 0, None] * ze0[:, 0]
        tm2[:, 0] = gez[:, 0, None] * ze0[:, 0]
        with np.errstate(divide="ignore", invalid="ignore"):
            z[:, :, i] = np.where((g > _EPS)[:, :, None], tm1 / g[:, :, None], 0.)
            ze[:, :, i] = np.where((ge > _EPS)[:, :, None], tm2 / ge[:, :, None], 0.)
    st.z[xm, 0:T, :, :7] = z[:, 0:T]; st.ze[xm, 0:T, :, :7] = ze[:, 0:T]
    # ---- 平均標準報酬額 w / we ----
    cht = _cht_table(ctx, k, xm)                             # (4, n)
    cht_h = cht * _houjou_factor(ctx, k)                     # 標準報酬上限の見直し（レバー houjou）。t = 0 の chwd には掛けない（港の順）
    cht_t = cht_h.copy()                                     # t ≥ 1 用（女 20〜49 歳は 2 種の比率）
    if s == 2:
        m = (xm >= 20) & (xm <= 49)
        cht_t[:, m] = cht_t[:, m] * (1. + K.jiiku[k, xm[m]])[None, :]
    chs = np.stack([np.where(xm <= 67, 1. + E.hh[k], 1. + E.ci[k]), np.ones(n),
                    1. + E.ci2[k, np.maximum(xm, 67)], np.full(n, 1. + E.hh[k])])   # (4, n)
    ch9 = h1
    chwd = bb[:, :, None] / 2. * cht_t.T[:, None, :]
    chwd[:, 0] = bb[:, 0, None] / 2. * cht.T
    if pseid == 0:
        chwd[xm >= hihonen] = 0.
    st.chwd[xm, 0:T] = chwd[:, 0:T]
    w = np.zeros((n, NT, 5, 4)); we = np.zeros((n, NT, 5, 4))
    w0 = np.zeros((n, NT, 5, 4)); we0 = np.zeros((n, NT, 5, 4))
    w0[:, Ts] = w_old[xm - 1, 0:T - 1, 0, :5]
    w0[:, T - 1] = np.where(w0[:, T - 1] <= _EPS, w_old[xm - 1, T - 1, 0, :5], w0[:, T - 1])
    we0[:, 0:T] = we_old[xm - 1, 0:T, 0, :5]
    brpos = (hs.br[k - 1, xm - 1, s] > _EPS)[:, None]
    with np.errstate(divide="ignore", invalid="ignore"):
        for ii in range(4):
            c_t = cht_t[ii][:, None]; c_0 = cht_h[ii][:, None]
            cs = chs[ii][:, None]
            tm1 = (gn[:, :, None] * we0[:, :, 1:5, ii] + gz[:, :, None] * w0[:, :, 1:5, ii]) * cs[:, :, None]
            tm2 = (gez[:, :, None] * we0[:, :, 1:5, ii] + y1[:, :, None] * w0[:, :, 1:5, ii]) * cs[:, :, None]
            # j = 4（新規加入の報酬を足す）。t ≥ 1 と t = 0 で式が違う
            if kou2:
                add1 = (bn[:, None] * ad * (gn - gnpt) + bnpt[:, None] * ad * gnpt) / 2. * c_t
                tmp = np.where(brpos, bbnp0 * (1. + brr[:, None]) * ch9 / 2. * (gz - gzpt) + bbpt0 * ch9 * gzpt,
                               (bbnp0 * ch9 + bbnp) / 2. * (gz - gzpt) + (bbpt0 * ch9 + bbpt) / 2. * gzpt)
                tmq = (bbnp0 * ch9 * (y1 - ypt1) + bbpt0 * ch9 * ypt1) / 2.
                add1_0 = (bn * (g[:, 0] - gpt[:, 0]) + bnpt * gpt[:, 0]) / 2. * ad * cht_h[ii]
            else:
                add1 = bn[:, None] * ad / 2. * gn * c_t
                tmp = np.where(brpos, bb0 * (1. + brr[:, None]) * ch9 / 2. * gz, (bb0 * ch9 + bb) / 2. * gz)
                tmq = bb0 * ch9 / 2. * y1
                add1_0 = bn * ad / 2. * g[:, 0] * cht_h[ii]
            gt15 = (xm > 15)[:, None]
            tm1[:, Ts, 3] += add1[:, Ts] + np.where(gt15, tmp[:, Ts] * c_t, 0.)
            tm2[:, Ts, 3] += np.where(gt15, tmq[:, Ts] * c_t, 0.)
            tm1[:, 0, 3] += add1_0
            w[:, :, 1:5, ii] = np.where((g > _EPS)[:, :, None], tm1 / g[:, :, None], 0.)
            we[:, :, 1:5, ii] = np.where((ge > _EPS)[:, :, None], tm2 / ge[:, :, None], 0.)
            w[:, :, 0, ii] = w[:, :, 1, ii] + w[:, :, 2, ii] + w[:, :, 3, ii]
            we[:, :, 0, ii] = we[:, :, 1, ii] + we[:, :, 2, ii] + we[:, :, 3, ii]
    if np.isnan(w[:, 0:T]).any():
        raise ValueError("simlbzw: w が nan (s=%d k=%d)" % (s, k))
    st.w[xm, 0:T, 0, :5] = w[:, 0:T]; st.we[xm, 0:T, 0, :5] = we[:, 0:T]


# ================================================================ 裁定時の資格・年齢・報酬比例額

def _it_of(ctx, coh, t1, t2, t3, t4):
    """資格の種類 it（1 新法25年 / 2 旧法中高齢 / 3 20年 / 4 該当なし）。港: dsitk.py:212-239"""
    D = ctx.C["dsitk"]
    th25 = _steps(D["kikan_25"], coh)
    thc = _steps(D["kikan_chukorei"], coh)
    it = np.full(np.broadcast(coh, t1).shape, 4, dtype=int)
    it = np.where((coh >= D["it3_cohort_from"]) & (t1 >= D["it3_years"] - _EPS), 3, it)
    it = np.where((t2 >= thc - _EPS) | (t1 >= th25 - _EPS), 1, it)
    it = np.where((t4 >= thc - _EPS) | (t3 >= th25 - _EPS), 2, it)
    return it


def _steps(points, coh):
    coh = np.asarray(coh)
    out = np.full(coh.shape, float(points[sorted(points, key=int)[0]]))
    for key, val in sorted((int(a), b) for a, b in points.items()):
        out = np.where(coh >= key, float(val), out)
    return out


def _ages(ctx, coh, it):
    """裁定時の支給開始年齢 (xr, xxr, xrb)。港: dsitk.py:244-322"""
    D = ctx.C["dsitk"]
    s2, konen = ctx.s, ctx.konen
    xr = np.full(np.shape(it), 60)
    if konen == 1:
        xr = np.where(it == 2, _steps(D["xr_kyuho"], coh).astype(int), xr)
    male = (it != 2) & (s2 == 1) if konen == 1 else np.ones(np.shape(it), dtype=bool)
    female = (it != 2) & (s2 == 2) & (konen == 1)
    xxr = np.where(male, ctx.sk_male.xxr(coh), np.where(female, ctx.sk_female.xxr(coh), ctx.sk_total.xxr(coh)))
    xxr = np.maximum(xr, xxr)
    xrb = np.where(male, ctx.sk_male.xrb(coh), np.where(female, ctx.sk_female.xrb(coh), xxr))
    xrb = np.maximum(xr, xrb)
    return xr, xxr, xrb


def dsitk(ctx, st, k, x, ii):
    """年齢 x の全経過年 t について (it, xr, xxr, xrb, tn, ta, tz, bk, bk2, bk3) を返す。
    `x` は配列でもよい（ii = 9/15/16/17 で使う）。港: emp_kyufu/dsitk.py:dsitk"""
    sd, E = ctx.sd, ctx.E
    hik = float(ctx.pol.get("kounen.rates.hikrate"))
    xa = np.atleast_1d(np.asarray(x))
    coh = YEARS.label(k) - xa
    ci = cohort_index(k, xa)
    pro = sd.pre[ci]; pros = sd.pres[ci]
    zero = np.zeros((len(xa), NT))
    if ii in (1, 2):
        Z = st.ze if ii == 1 else st.z
        W = st.we if ii == 1 else st.w
        zz = Z[xa]                                          # (x, t, 2, 10)
        t1, t2, t3, t4 = zz[..., 0, 0], zz[..., 0, 5], zz[..., 1, 0], zz[..., 1, 5]
        it = _it_of(ctx, coh[:, None], t1, t2, t3, t4)
        xr, xxr, xrb = _ages(ctx, coh[:, None], it)
        tz1 = zz[..., 0, 0] - zz[..., 0, 2] - zz[..., 0, 3] - zz[..., 0, 4]
        tz2 = zz[..., 0, 2] + zz[..., 0, 3] + zz[..., 0, 4]
        tz3 = zz[..., 0, 1] + zz[..., 0, 2] + zz[..., 0, 3]
        tz4 = zz[..., 0, 0] - zz[..., 0, 4]
        tn = np.minimum(zz[..., 0, 0], sd.can2[ci][:, None])
        ta = zz[..., 0, 6]
        with np.errstate(divide="ignore", invalid="ignore"):
            tmq = np.where(tz3 > _EPS, tz4 / tz3, 0.)
        ww = W[xa, :, 0]                                    # (x, t, 8, 4)
        bk = (ww[..., 0, 0] * tmq * pro[:, None] + ww[..., 4, 0] * pros[:, None]) * hik
        bk2 = ww[..., 0, 2] * tmq * pro[:, None] + ww[..., 4, 2] * pros[:, None]
        bk3 = (ww[..., 0, 3] * tmq * pro[:, None] + ww[..., 4, 3] * pros[:, None]) * hik * 0.8
        return it, xr, xxr, xrb, tn, ta, tz1, tz2, bk, bk2, bk3
    if ii in (9, 15, 16):
        xs = np.where(xa < ctx.xend, xa, xa - 1)
        zz = st.z[xs, :, :, :7].copy()                      # (x, t, 2, 7)
        ch = np.zeros((len(xa), 2, 7))
        for j in range(7):
            cond = (j == 0) | (j == 4) | ((ctx.s == 1) & (xa >= 40) & (j == 5)) | ((ctx.s >= 2) & (xa >= 35) & (j == 5)) | ((xa >= 20) & (xa <= 60) & (j == 6))
            ch[:, 0, j] = np.where(cond, 0.5, 0.)
            if ctx.s == 3:
                ch[:, 1, j] = ch[:, 0, j]
        zd = np.maximum(0., zz - ch[:, None, :, :])
        ww = st.w[xs, :, 0]
        wd = ww[..., 0, :]                                  # (x, t, 4)
        wd2 = np.maximum(0., ww[..., 4, :] - st.chwd[xs])
        tz1 = zd[..., 0, 0] - zd[..., 0, 2] - zd[..., 0, 3] - zd[..., 0, 4]
        tz2 = zd[..., 0, 2] + zd[..., 0, 3] + zd[..., 0, 4]
        z00 = zd[..., 0, 0]
        prb, prbs = sd.pre[cohort_index(ctx.KIJ, 0)], sd.pres[cohort_index(ctx.KIJ, 0)]   # 1946 年度生以降の乗率
        with np.errstate(divide="ignore", invalid="ignore"):
            if ii == 9:
                full = wd * prb + wd2 * prbs
                part = np.where((z00 > _EPS)[..., None], full * 25. / np.minimum(z00, 25.)[..., None], 0.)
                b = np.where((z00 >= 25.)[..., None], full, part)
            elif ii == 15:
                full = wd * pro[:, None, None] + wd2 * pros[:, None, None]
                fullb = wd * prb + wd2 * prbs
                part = np.where((z00 > _EPS)[..., None], fullb * 25. / np.minimum(z00, 25.)[..., None], 0.)
                b = np.where((z00 >= 25.)[..., None], full, part)
            else:
                b = wd * prb + wd2 * prbs
        bk = b[..., 0] * hik; bk2 = b[..., 2]; bk3 = b[..., 3] * hik * 0.8
        it = np.full((len(xa), NT), 4); xr = np.zeros((len(xa), NT), dtype=int)
        return it, xr, xr, xr, zero, zero, tz1, tz2, bk, bk2, bk3
    if ii == 17:
        zz = st.ze[xa]
        t1, t2, t3, t4 = zz[..., 0, 0], zz[..., 0, 5], zz[..., 1, 0], zz[..., 1, 5]
        it = _it_of(ctx, coh[:, None], t1, t2, t3, t4)
        xr, xxr, xrb = _ages(ctx, coh[:, None], it)
        tz1 = zz[..., 0, 0] - zz[..., 0, 2] - zz[..., 0, 3] - zz[..., 0, 4]
        tz2 = zz[..., 0, 2] + zz[..., 0, 3] + zz[..., 0, 4]
        ww = st.we[xa, :, 0]
        bk = (ww[..., 0, 0] * pro[:, None] + ww[..., 4, 0] * pros[:, None]) * hik
        bk2 = ww[..., 0, 2] * pro[:, None] + ww[..., 4, 2] * pros[:, None]
        bk3 = (ww[..., 0, 3] * pro[:, None] + ww[..., 4, 3] * pros[:, None]) * hik * 0.8
        return it, xr, xxr, xrb, zero, zero, tz1, tz2, bk, bk2, bk3
    raise ValueError(ii)


# ================================================================ 障害・遺族の裁定

def _srv_of(ctx, v):
    """遺族の給付割合（配偶者が 65 歳以上なら割り増し）。港: simlsaite1.py:_srv"""
    Z = ctx.C["izoku65"]
    f = Z["srv_male"] if ctx.s != 2 else Z["srv_female"]
    return np.where(np.asarray(v) >= 65, ctx.sd.srv * f, ctx.sd.srv)


def _cadt_ns(ctx, k, x):
    """配偶者（`ns` 歳差）の生年度で引く中高齢寡婦加算。"""
    ns = _rnd(ctx.K.ns[k, x]).astype(int)
    return ctx.sd.cadt[cohort_index(k, ns)]


def saitesho(ctx, st, k):
    """障害厚生年金の新規裁定（i = 9）。港: emp_kyufu/simlsaite1.py:saitesho"""
    T = ctx.tend
    xm = np.arange(15, ctx.xend + 1)
    E, sd, K = ctx.E, ctx.sd, ctx.K
    it, xr, xxr, xrb, tn, ta, tz1, tz2, bk, bk2, bk3 = dsitk(ctx, st, k, xm, 9)
    tmg = st.y[xm, 0:T, 2]                                   # (x, t)
    bk, bk2, bk3, tz1, tz2 = bk[:, 0:T], bk2[:, 0:T], bk3[:, 0:T], tz1[:, 0:T], tz2[:, 0:T]
    cl = K.cl[k]
    g1, g2, g3 = tmg * cl[1], tmg * cl[2], tmg * cl[3]
    bd = E.bd[k]
    st.rn[xm, 0, 9] += tmg.sum(1)
    st.hnn[xm, 0, 9, 1] += (tmg * tz1).sum(1)
    st.hnn[xm, 0, 9, 2] += (tmg * tz2).sum(1)
    hb = g1 * sd.ha[1] + g2 * sd.ha[2]
    st.fn[xm, 0, 9, 1] += (hb * bk).sum(1)
    st.fnhik[xm, 0, 9, 1] += (hb * bk2).sum(1)
    st.fnmin[xm, 0, 9, 1] += (hb * bk3).sum(1)
    st.fn[xm, 0, 9, 14] += hb.sum(1) * sd.fl1 * bd[14]
    s12 = (g1 + g2).sum(1)
    st.fn[xm, 0, 9, 21] += s12 * sd.adt[2] * bd[21]
    st.fn[xm, 0, 9, 4] += s12 * sd.adt[1] * bd[4]
    st.fn[xm, 0, 9, 6] += s12 * _cadt_ns(ctx, k, xm) * bd[6]
    h3 = g3 * sd.ha[3]
    st.fn[xm, 0, 9, 10] += (h3 * bk).sum(1)
    st.fnhik[xm, 0, 9, 10] += (h3 * bk2).sum(1)
    st.fnmin[xm, 0, 9, 10] += (h3 * bk3).sum(1)
    st.fn[xm, 0, 9, 12] += h3.sum(1) * sd.minb * bd[12] * sd.ema[ctx.s]


def _add_izoku(st, v, tmg, tz1, tz2, f1, f2, f3, extra):
    """遺族（i = 11）を配偶者の年齢 v（x ごと）に散らして足す。"""
    np.add.at(st.rn, (v, 0, 11), tmg)
    np.add.at(st.hnn, (v, 0, 11, 1), tz1)
    np.add.at(st.hnn, (v, 0, 11, 2), tz2)
    np.add.at(st.fn, (v, 0, 11, 1), f1)
    np.add.at(st.fnhik, (v, 0, 11, 1), f2)
    np.add.at(st.fnmin, (v, 0, 11, 1), f3)
    for j, val in extra:
        np.add.at(st.fn, (v, 0, 11, j), val)


def saiteizohiho(ctx, st, k):
    """被保険者が死亡したときの遺族厚生年金。港: emp_kyufu/simlsaite1.py:saiteizohiho"""
    T = ctx.tend
    s, s2 = ctx.s, ctx.s
    xm = np.arange(15, ctx.xend + 1)
    E, sd, K, rs = ctx.E, ctx.sd, ctx.K, ctx.rs
    bd = E.bd[k]
    KIJ = ctx.KIJ
    _, _, _, _, _, _, tz1, tz2, bka, bka2, bka3 = dsitk(ctx, st, k, xm, 15)
    _, _, _, _, _, _, tz1, tz2, bkb, bkb2, bkb3 = dsitk(ctx, st, k, xm, 16)
    it7, _, _, xrb7, _, _, tz1_7, tz2_7, bk7, bk7_2, bk7_3 = dsitk(ctx, st, k, xm, 17)
    y3 = st.y[xm, 0:T, 3]; ye = st.ye[xm, 0:T]
    mb = np.maximum(bkb, bka)[:, 0:T]; mb2 = np.maximum(bkb2, bka2)[:, 0:T]; mb3 = np.maximum(bkb3, bka3)[:, 0:T]
    cond7 = (np.isin(it7, (1, 2, 3)) & ((xm[:, None] <= np.maximum(60, xrb7))
                                       | ((k <= KIJ + 13) & (xm[:, None] <= 69 + k - KIJ))))[:, 0:T]
    for p in (0, 1):
        if p == 1 and s != 2:
            continue
        jj = 2 * p
        yx = K.yx[k, xm, p]
        v0 = yx.astype(int); frac = yx - v0
        rsx = rs[s, k, xm, 1 + jj]
        for bin1 in (0, 1):
            v = v0 + bin1
            srv = _srv_of(ctx, v)
            w = ((1. - frac) if bin1 == 0 else frac)
            tmg = y3 * (rsx * w)[:, None]                    # (x, t)
            g = tmg.sum(1)
            extra = [(14, g * sd.fl1 * bd[14]), (21, g * sd.adt[2] * bd[21])]
            if s2 != 2:
                m19 = v >= 19
                extra += [(7, np.where(m19, g * sd.wif * bd[7], 0.)),
                          (8, np.where(m19, g * sd.wife[cohort_index(k, v)] * bd[8], 0.))]
            _add_izoku(st, v, g, (tmg * tz1[:, 0:T]).sum(1), (tmg * tz2[:, 0:T]).sum(1),
                       (tmg * mb).sum(1) * srv, (tmg * mb2).sum(1) * srv, (tmg * mb3).sum(1) * srv, extra)
            # 受給待期中の死亡
            tmg = np.where(cond7, ye * (rsx * w)[:, None], 0.)
            g = tmg.sum(1)
            extra = []
            if s2 != 2:
                m19 = v >= 19
                extra = [(7, np.where(m19, g * sd.wif * bd[7], 0.)),
                         (8, np.where(m19, g * sd.wife[cohort_index(k, v)] * bd[8], 0.))]
            _add_izoku(st, v, g, (tmg * tz1_7[:, 0:T]).sum(1), (tmg * tz2_7[:, 0:T]).sum(1),
                       (tmg * bk7[:, 0:T]).sum(1) * srv, (tmg * bk7_2[:, 0:T]).sum(1) * srv,
                       (tmg * bk7_3[:, 0:T]).sum(1) * srv, extra)


def _reval_chain(ctx, k, ages):
    """68 歳以上の年数ぶんの賃金／物価の再評価の積 A[x]（x ≤ 67 は 1）。港: simlsaite1.py:295-307"""
    E = ctx.E
    A = np.ones(NX)
    x = np.arange(NX)
    fac = np.ones(NX)
    for kk in range(0, NX - 68 + 1):
        m = k - kk
        if kk <= k - 5:
            f = (1. + E.hh[m]) / (1. + E.ci[m])
        elif kk <= k - 2:
            f = 1. + E.hh2[m - 2]                            # m = 2, 3, 4 → 特例の 3 年
        else:
            f = 1.
        fac = np.where(x - 68 >= kk, fac * f, fac)
    return fac


def saiteizojuk(ctx, st, k):
    """受給者が死亡したときの遺族厚生年金。港: emp_kyufu/simlsaite1.py:saiteizojuk"""
    s, s2, pseid = ctx.s, ctx.s, ctx.pseid
    E, sd, K, rs, C = ctx.E, ctx.sd, ctx.K, ctx.rs, ctx.C
    KIJ = ctx.KIJ
    bd = E.bd[k]
    xm = np.arange(15, NX)
    n = len(xm)
    dx = np.maximum(xm, 67)
    l = st.l
    with np.errstate(divide="ignore", invalid="ignore"):
        tmq3 = np.where((xm > 70) & (l[k - 1, s, xm - 1] > _EPS),
                        (1. + l[k, s, xm] / l[k - 1, s, xm - 1]) * K.u[k, xm, 3] / 2., 0.)
    riv = np.where(xm <= 67, 1. + E.hh[k], 1. + E.ci[k])
    A = _reval_chain(ctx, k, xm)
    coh_x = YEARS.label(k) - xm
    R = C["riv2"]
    c_x = coh_x >= R["cohort"]
    q1 = K.q[k, xm, 1]; qd = K.q[k, xm, 2]
    cl, cl2 = K.cl[k], K.cl2[k]
    old = pseid == 0
    late = (xm >= 70 + k - KIJ) & old                       # 足元で既に 70 歳以上だった人
    c1 = 1. + E.ci2[k, dx]; c2 = 1. + E.hh[k]
    r, hn, f, fh, fm = st.r, st.hn, st.f, st.f_hik, st.f_min
    xp = xm - 1
    for p in (0, 1):
        if p == 1 and s != 2:
            continue
        jj = 2 * p
        yx = K.yx[k, xm, p]
        v0 = yx.astype(int); frac = yx - v0
        rsx = rs[s, k, xm, 1 + jj]; rsd = rs[s, k, xm, 2 + jj]
        for bin1 in (0, 1):
            v = v0 + bin1
            w = (1. - frac) if bin1 == 0 else frac
            srv = _srv_of(ctx, v)
            coh_v = YEARS.label(k) - v
            c_v = coh_v >= R["cohort"]
            riv2 = np.where(c_x & ~c_v, 1. / R["factor"], np.where(~c_x & c_v, R["factor"], 1.))
            tmrv = A[xm] / A[np.clip(v, 0, NX - 1)]
            tmrv = tmrv * np.where(c_x, 1. / R["factor"], 1.) * np.where(c_v, R["factor"], 1.)
            m19 = (v >= 19) & (s2 != 2)
            wife_v = sd.wife[cohort_index(k, v)]

            def push(tmg, th1, th2, tf, tf2, tf3, tmtu=None):
                tmg = tmg * w; th1 = th1 * w; th2 = th2 * w; tf = tf * w; tf2 = tf2 * w; tf3 = tf3 * w
                base = tmg if tmtu is None else tmtu * w
                extra = [(14, base * sd.fl1 * bd[14]), (21, base * sd.adt[2] * bd[21]),
                         (7, np.where(m19, base * sd.wif * bd[7], 0.)),
                         (8, np.where(m19, base * wife_v * bd[8], 0.))]
                _add_izoku(st, v, tmg, th1, th2, tf, tf2, tf3, extra)

            m45 = xm >= 45
            # ---- 老齢（i = 1, 2, 5, sen）----
            for (ia, ib, i5) in ((1, 2, 5), (3, 4, 7)):
                qq = (q1 * rsx)[:, None]
                rr = r[xp, :, ia] * qq                       # (x, xx)
                hh1 = hn[xp, :, ia, 1] * qq; hh2 = hn[xp, :, ia, 2] * qq
                ff = f[xp, :, ia, 1] * (riv * srv * q1 * rsx * tmrv)[:, None]
                ff2 = fh[xp, :, ia, 1] * (c1 * srv * q1 * rsx * riv2)[:, None]
                ff3 = fm[xp, :, ia, 1] * (c2 * srv * q1 * rsx * riv2)[:, None]
                if old:
                    qb = np.where(late, tmq3 * rsx, 0.)[:, None]
                    rr = rr + r[xp, :, ib] * qb
                    hh1 = hh1 + hn[xp, :, ib, 1] * qb; hh2 = hh2 + hn[xp, :, ib, 2] * qb
                    ff = ff + f[xp, :, ib, 1] * (riv * srv * tmrv)[:, None] * qb
                    ff2 = ff2 + fh[xp, :, ib, 1] * (c1 * srv * riv2)[:, None] * qb
                    ff3 = ff3 + fm[xp, :, ib, 1] * (c2 * srv * riv2)[:, None] * qb
                tmg = rr.sum(1) + r[xp, 0, i5] * q1 * rsx
                th1 = hh1.sum(1) + hn[xp, 0, i5, 1] * q1 * rsx
                th2 = hh2.sum(1) + hn[xp, 0, i5, 2] * q1 * rsx
                tf = ff.sum(1) + f[xp, 0, i5, 1] * riv * srv * q1 * rsx * tmrv
                tf2 = ff2.sum(1) + fh[xp, 0, i5, 1] * c1 * srv * q1 * rsx * riv2
                tf3 = ff3.sum(1) + fm[xp, 0, i5, 1] * c2 * srv * q1 * rsx * riv2
                tmtu = None
                if ia == 1:
                    sen = (xm >= 61) & (xm <= 70)
                    tmg = tmg + np.where(sen, st.rsen[xp] * q1 * rsx, 0.)
                    th1 = th1 + np.where(sen, st.hnsen[xp, 1] * q1 * rsx, 0.)
                    th2 = th2 + np.where(sen, st.hnsen[xp, 2] * q1 * rsx, 0.)
                    tf = tf + np.where(sen, st.fsen[xp, 1] * riv * srv * q1 * rsx * tmrv, 0.)
                    tf2 = tf2 + np.where(sen, st.fsenhik[xp, 1] * c1 * srv * q1 * rsx * riv2, 0.)
                    tf3 = tf3 + np.where(sen, st.fsenmin[xp, 1] * c2 * srv * q1 * rsx * riv2, 0.)
                else:
                    tmtu = (f[xp, :, 3, 4] / (sd.adt[1] * E.bd[k - 1, 4]) * qq).sum(1)
                    tmtu = np.where(m45, tmtu, 0.)
                push(np.where(m45, tmg, 0.), np.where(m45, th1, 0.), np.where(m45, th2, 0.),
                     np.where(m45, tf, 0.), np.where(m45, tf2, 0.), np.where(m45, tf3, 0.), tmtu)
            # ---- 障害（i = 9, 10）----
            cs = cl[1] + cl[2]; cs2 = cl2[1] + cl2[2]
            qd_ = qd * rsd
            tmg = r[xp, 0, 9] * qd_ * cs + r[xp, 0, 10] * qd_ * cs2
            th1 = hn[xp, 0, 9, 1] * qd_ * cs + hn[xp, 0, 10, 1] * qd_ * cs2
            th2 = hn[xp, 0, 9, 2] * qd_ * cs + hn[xp, 0, 10, 2] * qd_ * cs2
            if cs > _EPS:
                prb = sd.pre[cohort_index(KIJ, 0)]; pra = sd.pre[cohort_index(KIJ, NX - 1)]
                kyu = prb / pra * C["kyu_shogai_ratio"]
                d1 = cs / (cl[1] * sd.ha[1] + cl[2] * sd.ha[2]); d2 = cs2 / (cl2[1] * sd.hb[1] + cl2[2] * sd.hb[2])
                tf = f[xp, 0, 9, 1] * qd_ * riv * srv * d1 * tmrv + f[xp, 0, 10, 1] * kyu * qd_ * riv * srv * d2 * tmrv
                tf2 = fh[xp, 0, 9, 1] * c1 * qd_ * srv * d1 * riv2 + fh[xp, 0, 10, 1] * c1 * kyu * qd_ * srv * riv2 * d2
                tf3 = fm[xp, 0, 9, 1] * c2 * qd_ * srv * d1 * riv2 + fm[xp, 0, 10, 1] * c2 * kyu * qd_ * srv * d2 * riv2
            else:                                             # E30: 港は tmf2/tmf3 を持ち越す。高速版は 0
                tf = tf2 = tf3 = np.zeros(n)
            tmg = tmg * w; th1 = th1 * w; th2 = th2 * w; tf = tf * w; tf2 = tf2 * w; tf3 = tf3 * w
            extra = [(7, np.where(m19, tmg * sd.wif * bd[7], 0.)), (8, np.where(m19, tmg * wife_v * bd[8], 0.))]
            _add_izoku(st, v, tmg, th1, th2, tf, tf2, tf3, extra)


# ================================================================ 老齢の裁定

def _ris_kuriage(ctx, k, x, xxr, ris_i, keep_ge):
    """繰上げの選択率 ris[xx]（xx 0..5）を経過年ごとに。`xxr` は (t,) 配列。
    `keep_ge`: True なら 65−xx ≥ x（在職）、False なら x ≤ 65−xx（退職）を残す。"""
    nt = len(xxr)
    ris = np.zeros((nt, 6))
    ris[:, 0] = 1.
    for xx in range(1, 6):
        ris[:, xx] = np.where(xxr > 65 - xx, ctx.ku.riss[65 - xx, np.clip(xxr, 60, 65), ctx.s, ris_i], 0.)
    ris[:, 0] -= ris[:, 1:].sum(1)
    keep = np.array([(65 - xx >= x) if keep_ge else (x <= 65 - xx) for xx in range(6)])
    ris = ris * keep[None, :]
    tot = ris.sum(1)
    with np.errstate(divide="ignore", invalid="ignore"):
        ris = np.where((tot >= _EPS)[:, None], ris / tot[:, None], np.array([1., 0, 0, 0, 0, 0])[None, :])
    return ris


def _teigaku_terms(ctx, k, x, tmg, tn, ta, bd):
    """定額部分 `tmf`、基礎年金相当 `tmo`（(xx, t) の配列）。"""
    sd = ctx.sd
    ci = cohort_index(k, x)
    tmf = tmg * sd.fl * sd.flt[ci] * bd[2] * tn
    tmo = tmg * sd.fl1 * bd[14] * np.minimum(ta / sd.can[ci], 1.)
    if ctx.flg_sigo >= 1:
        tmo = tmo * max(sd.can[ci], 40.) / 40.
    return tmf, tmo


def _add_rou(ctx, st, k, x, i, tmg, tz1, tz2, bk, bk2, bk3, tn, ta, tmgp=None, with3=True, tosen=False):
    """老齢の新規裁定を rn/hnn/fn に足す。tmg: (xx, t)。`tosen` は長期加入者の特例（xx 無し）。"""
    sd, E = ctx.sd, ctx.E
    bd = E.bd[k]
    tmf, tmo = _teigaku_terms(ctx, k, x, tmg, tn, ta, bd)
    ci = cohort_index(k, x)
    cad = _cadt_ns(ctx, k, x)
    g = tmg.sum(-1)
    gp = g if tmgp is None else g - tmgp.sum(-1)
    if tosen:
        st.rsenn[x] += g; st.hnsenn[x, 1] += (tmg * tz1).sum(); st.hnsenn[x, 2] += (tmg * tz2).sum()
        st.fsenn[x, 1] += (tmg * bk).sum(); st.fsennhik[x, 1] += (tmg * bk2).sum(); st.fsennmin[x, 1] += (tmg * bk3).sum()
        st.fsenn[x, 2] += tmf.sum(); st.fsenn[x, 14] += tmo.sum(); st.fsenn[x, 3] += np.maximum(tmf - tmo, 0.).sum()
        st.fsenn[x, 4] += g * sd.adt[1] * bd[4]; st.fsenn[x, 23] += g * sd.sadt[ci] * bd[23]
        st.fsenn[x, 5] += g * sd.adt[2] * bd[5]; st.fsenn[x, 6] += g * cad * bd[6]
        return
    st.rn[x, :, i] += g
    st.hnn[x, :, i, 1] += (tmg * tz1).sum(-1); st.hnn[x, :, i, 2] += (tmg * tz2).sum(-1)
    st.fn[x, :, i, 1] += (tmg * bk).sum(-1); st.fnhik[x, :, i, 1] += (tmg * bk2).sum(-1); st.fnmin[x, :, i, 1] += (tmg * bk3).sum(-1)
    st.fn[x, :, i, 2] += tmf.sum(-1)
    st.fn[x, :, i, 14] += tmo.sum(-1)
    if with3:
        st.fn[x, :, i, 3] += np.maximum(tmf - tmo, 0.).sum(-1)
    st.fn[x, :, i, 4] += gp * sd.adt[1] * bd[4]
    st.fn[x, :, i, 23] += gp * sd.sadt[ci] * bd[23]
    st.fn[x, :, i, 5] += gp * sd.adt[2] * bd[5]
    st.fn[x, :, i, 6] += gp * cad * bd[6]


def saitezai(ctx, st, k):
    """在職のまま支給開始年齢に達した人の裁定（i = 2/4）。港: emp_kyufu/simlsaite2.py:saitezai"""
    s, pseid, xend, T = ctx.s, ctx.pseid, ctx.xend, ctx.tend
    KIJ = ctx.KIJ
    kou2 = ctx.kou2
    l, lpt = st.l, st.lpt
    gd_old = st.gd.copy()
    xs_all = np.arange(55, xend + 1)
    D = dsitk(ctx, st, k, xs_all, 2)
    for x in range(xend, 54, -1):
        keep = ~((st.z[x, 0:T, 0, 0] < 1. - _EPS) & (x < 65))
        if not keep.any():
            continue
        ix = x - 55
        it, xr, xxr, xrb, tn, ta, tz1, tz2, bk, bk2, bk3 = (a[ix, 0:T] for a in D)
        tmo = st.z[x, 0:T, 0, 0]
        base = ((x == xr) & (x < 65)) | ((x > xr) & (x < 65) & (x <= xrb) & (xrb > 60))
        c2 = base & ~np.isin(it, (3, 4))
        c4 = (base & np.isin(it, (3, 4)) & (tmo >= 1. - _EPS)) | ((x > xrb) & (x < 65) & (tmo >= 1. - _EPS) & (tmo < 2. - _EPS))
        i_t = np.where(c4, 4, np.where(c2, 2, 0))
        i_t = np.where(keep, i_t, 0)
        g = st.g[x, 0:T]
        q2 = st.q2[k, x]
        if (i_t > 0).any():
            ris = np.where((xr >= 60)[:, None], _ris_kuriage(ctx, k, x, xxr, 1, True), np.array([1., 0, 0, 0, 0, 0])[None, :])
            act = i_t > 0
            # 在職の待機 gd
            cond = (xrb > 60) & (x > 60) & (x <= xrb) & (np.arange(T) > 0)
            if k == KIJ + 1:
                tot = sum(st.r[x - 1, xx, 2] + st.r[x - 1, xx, 4] for xx in range(6)) * (1. - q2)
                with np.errstate(divide="ignore", invalid="ignore"):
                    gd = np.where(cond & (x < xrb), st.gd[x, 0:T] + tot * g / l[k, s, x], 0.)
            else:
                gd = np.zeros(T)
                gd[1:] = np.where(cond[1:], gd_old[x - 1, 0:T - 1] * (1. - q2), 0.)
            gd = np.where(act, gd, st.gd[x, 0:T])
            tmg = ris.T * (g - gd)[None, :]                   # (6, t)
            xxs = np.arange(6)
            if x < 60:
                tmg[1:] = 0.
            low = (xrb > 60) & (x < xrb)
            tmg = np.where(low[None, :] & (x != 65 - xxs)[:, None], 0., tmg)
            tmg = np.where(act[None, :], tmg, 0.)
            gd = gd + np.where(low, tmg.sum(0), 0.)
            st.gd[x, 0:T] = gd
            for i in (2, 4):
                m = (i_t == i)[None, :]
                tg = np.zeros((NXX, T)); tg[:6] = np.where(m, tmg, 0.)
                _add_rou(ctx, st, k, x, i, tg, tz1, tz2, bk, bk2, bk3, tn, ta, with3=False)
        # ---- 在職のまま裁定する年齢（65・70 歳、66〜69 歳）----
        taizai = (xend > x) and (x in (65, 70) or 66 <= x <= 69)
        if taizai:
            i_t = np.where(np.isin(it, (1, 2)), 2, 4)
            i_t = np.where(keep, i_t, 0)
            tml = l[k, s, x] + lpt[k, s, x] if kou2 else l[k, s, x]
            tmrp = (st.r[x - 1, :, 2] + st.r[x - 1, :, 4] + st.r[x - 1, :, 6] + st.r[x - 1, :, 8]) * (1. - q2)   # (16,)
            tmrps = tmrp.sum()
            ris = np.zeros(NXX)
            for xx in range(1, 11):
                if tml > _EPS and tml >= tmrps:
                    ris[xx] = tmrp[xx] / tml
                elif tmrps > _EPS:
                    ris[xx] = tmrp[xx] / tmrps
            ris[0] = 1. - ris[1:11].sum()
            if ris[0] < 0.:
                raise ValueError("saitezai: ris[0] < 0")
            tmg = ris[:, None] * g[None, :]
            tmg = np.where((i_t > 0)[None, :], tmg, 0.)
            tmgp = np.zeros_like(tmg)
            if kou2 and k >= ctx.partyr3 and lpt[k, s, x] > _EPS:
                ok = (x - k > xrb - ctx.partyr3) & (i_t > 0)
                tmgp = np.where(ok[None, :], ris[:, None] * st.gpt[x, 0:T][None, :] * ctx.lpt1[k, s, x] / lpt[k, s, x]
                                * ctx.K.rt[ctx.partyr3, np.clip(xrb, 0, NX - 1)][None, :], 0.)
            if kou2 and ctx.flg_part >= 1 and k >= ctx.partyr4 and lpt[k, s, x] > _EPS:   # 適用拡大（レバー）
                ok4 = (x - k > xrb - ctx.partyr4) & (i_t > 0)
                lopt = ctx.lpt2[k, s, x] + ctx.lpt3[k, s, x] + ctx.lpt4[k, s, x]
                tmgp = tmgp + np.where(ok4[None, :], ris[:, None] * st.gpt[x, 0:T][None, :] * lopt / lpt[k, s, x]
                                       * ctx.K.rt[ctx.partyr4, np.clip(xrb, 0, NX - 1)][None, :], 0.)
            for i in (2, 4):
                m = (i_t == i)[None, :]
                _add_rou(ctx, st, k, x, i, np.where(m, tmg, 0.), tz1, tz2, bk, bk2, bk3, tn, ta,
                         tmgp=np.where(m, tmgp, 0.), with3=True)


def saitetai(ctx, st, k):
    """退職しての裁定（i = 1/3）と長期加入者の特例。港: emp_kyufu/simlsaite2.py:saitetai"""
    s, pseid, xend, T = ctx.s, ctx.pseid, ctx.xend, ctx.tend
    KIJ = ctx.KIJ
    kou2 = ctx.kou2
    C = ctx.C["tai_bunkatsu"]
    l, lpt = st.l, st.lpt
    xxs = np.arange(NXX)
    xs_all = np.arange(55, xend + 1)
    D = dsitk(ctx, st, k, xs_all, 1)                      # 自分の x の ze だけを見るので先にまとめて
    for x in range(55, xend + 1):
        keep = ~((st.ze[x, 0:T, 0, 0] < 1. - _EPS) & (x < 65))
        if not keep.any():
            continue
        ix = x - 55
        it, xr, xxr, xrb, tn, ta, tz1, tz2, bk, bk2, bk3 = (a[ix, 0:T] for a in D)
        tmo = st.ze[x, 0:T, 0, 0]
        ge = st.ge[x, 0:T]
        sen = keep & (tmo >= ctx.sd.senll - _EPS) & (it != 2) & (x >= xrb) & (x < xxr) & (xxr > 60)
        if sen.any():
            tmg = np.where(sen, ge, 0.)
            _add_rou(ctx, st, k, x, 0, tmg, tz1, tz2, bk, bk2, bk3, tn, ta, tosen=True)
            ge = np.where(sen, 0., ge)
            st.ze[x, 0:T][sen] = 0.
            st.we[x, 0:T][sen] = 0.
        tai = keep & ~sen & (x >= xr)
        if not tai.any():
            st.ge[x, 0:T] = ge
            continue
        i_t = np.where(np.isin(it, (1, 2)), 1, 3)
        y1 = st.y[x, 0:T, 1]
        tmg2 = np.zeros((NXX, T))
        has = tai & (y1 > _EPS)
        if has.any():
            tmlp = l[k - 1, s, x - 1] + lpt[k - 1, s, x - 1] if kou2 else l[k - 1, s, x - 1]
            tmrp = st.r[x - 1, :, 2] + st.r[x - 1, :, 4] + st.r[x - 1, :, 6] + st.r[x - 1, :, 8]
            tmrps = tmrp.sum()
            caseA = has & ((xr < 60) | (tmlp <= _EPS))
            caseB = has & ~caseA & (x > xrb)
            caseC = has & ~caseA & ~caseB & (x <= xrb) & (xrb > 60)
            tmg2[0] += np.where(caseA, y1, 0.)
            if caseB.any():
                if tmrps >= tmlp:
                    risB = tmrp / tmrps
                    tb = risB[:, None] * y1[None, :]
                else:
                    risB = tmrp / tmlp
                    tb = risB[:, None] * y1[None, :]
                    tb[min(10, x - 60) if x > 65 else 0] += y1 * (tmlp - tmrps) / tmlp
                tmg2 += np.where(caseB[None, :], tb, 0.)
            if caseC.any():
                if tmrps - tmlp > _EPS:
                    raise ValueError("saitetai: tmrps > tmlp")
                risC = np.zeros((NXX, T))
                risC[0] = 1.; tmris = np.ones(T)
                for xx in range(1, 6):
                    if 65 - xx < x:
                        risC[xx] = tmrp[xx] / tmlp
                        risC[0] -= risC[xx]
                    else:
                        risC[xx] = ctx.ku.riss[65 - xx, np.clip(xxr, 60, 65), s, 0]
                        tmris -= risC[xx]
                tmris2 = risC[0].copy()
                risC[0] = tmris
                for xx in range(0, 65 - x + 1):
                    risC[xx] = risC[xx] * tmris2
                tc = np.zeros((NXX, T))
                for xx in range(1, 6):
                    if 65 - xx < x:
                        tc[xx] = y1 * risC[xx]
                tmg2 += np.where(caseC[None, :], tc, 0.)
            ged = tmg2.sum(0)
            ge = ge - np.where(has, ged, 0.)
            ge = np.where(has & (ge < _EPS) & (ge >= -_EPS), 0., ge)
        # 2 回めの ris（受給待期から裁定するぶん）
        ris = np.zeros((NXX, T)); ris[0] = 1.
        if 60 + k - KIJ <= x <= 69 + k - KIJ and x > 65:
            ris[:] = 0.; ris[min(15, x - 60)] = 1.
        else:
            m2 = (xr == 60) & (((xr <= x) & (x <= xrb)) | ((k == KIJ + 1) & (x <= xxr)))
            if m2.any():
                rr = np.zeros((6, T)); rr[0] = 1.
                for xx in range(1, 6):
                    rr[xx] = np.where(xx > 65 - xxr, ctx.ku.riss[65 - xx, np.clip(xxr, 60, 65), s, 0], 0.)
                rr[0] -= rr[1:].sum(0)
                keep6 = np.array([x <= 65 - xx for xx in range(6)])
                rr = rr * keep6[:, None]
                tot = rr.sum(0)
                with np.errstate(divide="ignore", invalid="ignore"):
                    rr = np.where((tot > _EPS)[None, :], rr / tot[None, :], np.array([1., 0, 0, 0, 0, 0])[:, None])
                ris[:6] = np.where(m2[None, :], rr, ris[:6])
        okxx = (x >= xrb)[None, :] | ((x == 65 - xxs) & (xxs <= 5))[:, None]
        if x < 60:
            okxx[1:] = False
        tmg = np.where(okxx, ris * ge[None, :], 0.)
        coh = YEARS.label(k) - x
        male_like = (pseid == 0 and s == 1) or pseid != 0
        cto = C["cohort_to_male"] if male_like else C["cohort_to_female"]
        if C["cohort_from"] <= coh <= cto:
            tmg = tmg / max(1., float(C["age_base"] - x))
        ged = tmg.sum(0)
        tmg = tmg + tmg2
        tmg = np.where(tai[None, :], tmg, 0.)
        for i in (1, 3):
            m = (i_t == i)[None, :]
            _add_rou(ctx, st, k, x, i, np.where(m, tmg, 0.), tz1, tz2, bk, bk2, bk3, tn, ta, with3=True)
        ge = ge - np.where(tai, ged, 0.)
        zz = tai & (np.abs(ge) < _EPS)
        ge = np.where(zz, 0., ge)
        if (ge[tai] <= -_EPS).any():
            raise ValueError("saitetai: ge < 0 (x=%d k=%d)" % (x, k))
        st.ze[x, 0:T][zz] = 0.
        st.we[x, 0:T][zz] = 0.
        st.ge[x, 0:T] = ge


def kyuho_move(ctx, st, k):
    """1925 年度以前の生まれの裁定を旧法（i + 4）へ。港: emp_kyufu/siml.py:siml 217-236"""
    xm = np.arange(55, ctx.xend + 1)
    coh = YEARS.label(k) - xm
    xo = xm[coh <= ctx.kyuho_last]
    if len(xo) == 0:
        return
    for i in (1, 2, 3, 4):
        m = st.rn[xo, :, i] > _EPS                          # (x, xx)
        for a in (st.rn, st.pshnn):
            a[xo, :, i + 4] = np.where(m, a[xo, :, i], a[xo, :, i + 4]); a[xo, :, i] = np.where(m, 0., a[xo, :, i])
        for jj in (1, 2):
            st.hnn[xo, :, i + 4, jj] = np.where(m, st.hnn[xo, :, i, jj], st.hnn[xo, :, i + 4, jj])
            st.hnn[xo, :, i, jj] = np.where(m, 0., st.hnn[xo, :, i, jj])
        st.fn[xo, :, i + 4, :] = np.where(m[..., None], st.fn[xo, :, i, :], st.fn[xo, :, i + 4, :])
        st.fn[xo, :, i, :] = np.where(m[..., None], 0., st.fn[xo, :, i, :])
        for j in (1, 10, 13, 22):
            for a in (st.fnhik, st.fnmin):
                a[xo, :, i + 4, j] = np.where(m, a[xo, :, i, j], a[xo, :, i + 4, j])
                a[xo, :, i, j] = np.where(m, 0., a[xo, :, i, j])


# ================================================================ 受給者を 1 歳進める

def _riv2_table(ctx, k):
    """68 歳超の `hp2` の年齢差の積 riv2[x]（x ≤ 67 は 1）。港: simlrhnf.py:241-247"""
    E = ctx.E
    x = np.arange(NX)
    riv2 = np.ones(NX)
    for kk in range(0, max(0, k - 5) + 1):
        m = x - 68 >= kk
        xk = np.clip(x - kk, 0, NX - 1)
        riv2 = np.where(m, riv2 * (1. + E.hp2[k - kk, xk]) / (1. + E.hp2[k - kk, 67]), riv2)
    return riv2


def simlrhnf(ctx, st, k):
    """受給者を 1 歳進める（13 給付 × 繰上げ区分 × 内訳を一度に）。港: emp_kyufu/simlrhnf.py:simlrhnf,
    simlrhnf0, simlrhnfsen, simlrhnfsen60"""
    s, s2, pseid, xend = ctx.s, ctx.s, ctx.pseid, ctx.xend
    KIJ = ctx.KIJ
    E, K, C = ctx.E, ctx.K, ctx.C
    x = np.arange(NX)
    dx = np.maximum(x, 67)
    q = K.q[k]; u = K.u[k]
    q2 = st.q2[k]
    l = st.l
    xxr = np.maximum(60, ctx.sk.xxr(YEARS.label(k) - x))
    # ---- 改定率（x × j）----
    riv_j = np.zeros((NX, NJ))
    riv_j[:, :] = (1. + E.hp2[k, dx])[:, None]
    for j in (1, 10):
        riv_j[:, j] = np.where(x <= 67, 1. + E.hh[k], 1. + E.ci[k])
    for j in _KKU_JS:
        riv_j[:, j] = 1. + E.hp2[k, 67]
    riv3 = 1. + E.ci2[k, dx]; riv4 = np.full(NX, 1. + E.hh[k]); riv5 = np.full(NX, 1. + E.hp2[k, 67])
    riv2 = _riv2_table(ctx, k)
    js = [j for j in range(1, NJ) if j not in (13, 22)]
    j110 = [1, 10]; jrest = [j for j in js if j not in (1, 10)]
    jnk = [j for j in jrest if j not in _KKU_JS]
    rivm = np.zeros((NX, NJ))                                # f_min の改定率
    rivm[:, j110] = riv4[:, None]; rivm[:, jrest] = riv5[:, None]
    # 新規裁定の 8 割下限と riv2 の補正（fn を書き換える）
    keep110 = st.fnmin[:, :, :, j110].copy()
    st.fnmin[:] = st.fn * 0.80
    st.fnmin[:, :, :, j110] = keep110
    fac2 = np.ones((NX, NJ)); fac2[:, jnk] = riv2[:, None]
    st.fn *= fac2[:, None, None, :]
    # ---- 残存率 tmo[x, i] ----
    tmo = np.zeros((NX, NI))
    tmo[:, [1, 3, 5, 7]] = (1. - q[:, 1])[:, None]
    zai = np.where((x > 55) & (x <= 60), np.exp(-u[:, 0]), np.where((x > 60) & (x <= xend - 1), 1. - q2, 0.))
    tmo[:, [2, 4]] = zai[:, None]
    late68 = x > 70 + k - KIJ
    tmo[:, [6, 8]] = np.where(late68, 1. - q[:, 1], zai)[:, None]
    stop = (x == 65) | ((xend > 70) & (x == 70)) | ((x >= 66) & (x <= 69) & (x < xend))
    tmo[stop, 2] = 0.; tmo[stop, 4] = 0.
    tmo[:, [9, 10]] = (1. - q[:, 2])[:, None]
    tmo[:, 11:] = (1. - q[:, 3])[:, None]
    tmo[0] = 0.
    late = (x >= 70 + k - KIJ) & (pseid == 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        xp = np.clip(x - 1, 0, NX - 1)
        tmp = np.where(late & (l[k - 1, s, xp] > _EPS),
                       np.maximum(0., q2 - (1. + l[k, s, x] / l[k - 1, s, xp]) * u[:, 3] / 2.), 0.)
    # 前年度の値は書き戻す前に読み切るので複製は要らない
    r_old, hn_old, pshn_old = st.r, st.hn, st.pshn
    f_old, fh_old, fm_old = st.f, st.f_hik, st.f_min
    P = slice(0, NX - 1); Q = slice(1, NX)                  # x−1 → x
    T4 = tmo[Q, None, :]
    rr = r_old[P] * T4 + st.rn[Q]
    hn = hn_old[P] * T4[..., None] + st.hnn[Q]
    ps = pshn_old[P] * T4 + st.pshnn[Q]
    ff = f_old[P] * (T4[..., None] * riv_j[Q, None, None, :]) + st.fn[Q]
    fh = fh_old[P][:, :, :, j110] * (T4[..., None] * riv3[Q, None, None, None]) + st.fnhik[Q][:, :, :, j110]
    fm = fm_old[P] * (T4[..., None] * rivm[Q, None, None, :]) + st.fnmin[Q]
    # 遺族の 65 歳の割り増し（i = 11, j = 1, 10）
    Z = C["izoku65"]
    fac_f = Z["f_male"] if s2 != 2 else Z["f_female"]
    fac_h = Z["fhik_male"] if s2 != 2 else Z["fhik_female"]
    i65 = 65 - 1
    for n, j in enumerate(j110):
        ff[i65, :, 11, j] = f_old[64, :, 11, j] * tmo[65, 11] * riv_j[65, j] * fac_f + st.fn[65, :, 11, j]
        fh[i65, :, 11, n] = fh_old[64, :, 11, j] * tmo[65, 11] * riv3[65] * fac_h + st.fnhik[65, :, 11, j]
        fm[i65, :, 11, j] = fm_old[64, :, 11, j] * tmo[65, 11] * riv4[65] * fac_h + st.fnmin[65, :, 11, j]
    # 長期加入者の特例を本流（i = 1, xx = 0, x = xxr）へ合流
    merge = (x == xxr) & (xxr > 60) & (x >= 1)
    mz = np.nonzero(merge)[0]
    if len(mz):
        t1 = tmo[mz, 1]
        rr[mz - 1, 0, 1] = (r_old[mz - 1, 0, 1] + st.rsen[mz - 1]) * t1 + st.rn[mz, 0, 1]
        hn[mz - 1, 0, 1, 1:3] = (hn_old[mz - 1, 0, 1, 1:3] + st.hnsen[mz - 1, 1:3]) * t1[:, None] + st.hnn[mz, 0, 1, 1:3]
        ps[mz - 1, 0, 1] = (pshn_old[mz - 1, 0, 1] + st.pshnsen[mz - 1]) * t1 + st.pshnn[mz, 0, 1]
        ff[mz - 1, 0, 1, :] = (f_old[mz - 1, 0, 1, :] + st.fsen[mz - 1]) * (t1[:, None] * riv_j[mz]) + st.fn[mz, 0, 1, :]
        fh[mz - 1, 0, 1, :] = ((fh_old[mz - 1, 0, 1, :][:, j110] + st.fsenhik[mz - 1][:, j110]) * (t1 * riv3[mz])[:, None]
                               + st.fnhik[mz, 0, 1, :][:, j110])
        fm[mz - 1, 0, 1, :] = (fm_old[mz - 1, 0, 1, :] + st.fsenmin[mz - 1]) * (t1[:, None] * rivm[mz]) + st.fnmin[mz, 0, 1, :]
    # 足元で 70 歳以上だった在職（i + 1）を退職（i = 1, 3）へ
    if pseid == 0:
        tp = tmp[Q, None]
        for i in (1, 3):
            rr[:, :, i] += r_old[P, :, i + 1] * tp
            hn[:, :, i, :] += hn_old[P, :, i + 1, :] * tp[..., None]
            ps[:, :, i] += pshn_old[P, :, i + 1] * tp
            ff[:, :, i, :] += f_old[P, :, i + 1, :] * (tp[..., None] * riv_j[Q, None, :])
            fh[:, :, i, :] += fh_old[P, :, i + 1, :][:, :, j110] * (tp * riv3[Q, None])[..., None]
            fm[:, :, i, :] += fm_old[P, :, i + 1, :] * (tp[..., None] * rivm[Q, None, :])
    # 書き戻し（j = 13, 22 は動かさない。f_hik は j = 1, 10 だけ）
    st.r[Q, :, 1:] = rr[:, :, 1:]; st.hn[Q, :, 1:, 1:3] = hn[:, :, 1:, 1:3]; st.pshn[Q, :, 1:] = ps[:, :, 1:]
    for j in (13, 22, 0):                                    # 動かさない内訳は前年度のまま
        ff[:, :, :, j] = f_old[Q, :, :, j]; fm[:, :, :, j] = fm_old[Q, :, :, j]
    st.f[1:, :, 1:, :] = ff[:, :, 1:, :]
    st.f_hik[1:, :, 1:, :][:, :, :, j110] = fh[:, :, 1:, :]
    st.f_min[1:, :, 1:, :] = fm[:, :, 1:, :]
    # x = 0（新規裁定だけ）
    st.r[0, 0, 1:] = st.rn[0, 0, 1:]; st.hn[0, 0, 1:, 1:3] = st.hnn[0, 0, 1:, 1:3]; st.pshn[0, 0, 1:] = st.pshnn[0, 0, 1:]
    st.f_hik[0, 0, 1:11, 1:] = 0.; st.f_min[0, 0, 1:11, 1:] = 0.
    for i in range(11, NI):
        st.f_hik[0, 0, i, j110] = st.fnhik[0, 0, i, j110]; st.f_min[0, 0, i, j110] = st.fnmin[0, 0, i, j110]
        st.f_hik[0, 0, i, (13, 22)] = 0.; st.f_min[0, 0, i, (13, 22)] = 0.; st.fn[0, 0, i, (13, 22)] = 0.
        st.fnmin[0, 0, i, jrest] = st.fn[0, 0, i, jrest] * 0.8
        st.f_min[0, 0, i, jrest] = st.fnmin[0, 0, i, jrest]
    st.f[0, 0, 1:, 1:] = st.fn[0, 0, 1:, 1:]
    if len(mz):
        st.rsen[mz - 1] = 0.; st.hnsen[mz - 1, 1:3] = 0.; st.pshnsen[mz - 1] = 0.
        st.fsen[np.ix_(mz - 1, js)] = 0.; st.fsenhik[np.ix_(mz - 1, j110)] = 0.; st.fsenmin[np.ix_(mz - 1, js)] = 0.
    # i = 12 の経過的な差額（j = 11）の下限
    xa = np.arange(19, NX)
    tmz = K.rc[k, xa]
    F = st.f[xa, 0, 12]
    tmx = F[:, 2] + F[:, 3] + F[:, 11] - F[:, 15] - F[:, 16] * 3. / 4. - F[:, 17] * tmz - F[:, 18] * (1. - tmz)
    fix = -F[:, 2] - F[:, 3] + F[:, 15] + F[:, 16] * 3. / 4. + F[:, 17] * tmz + F[:, 18] * (1. - tmz)
    st.f[xa, 0, 12, 11] = np.where(tmx < 0., fix, F[:, 11])
    # ---- 長期加入者の特例（70 → 61、最後に 60）----
    rsen_old, hnsen_old, pshnsen_old = st.rsen.copy(), st.hnsen.copy(), st.pshnsen.copy()
    fsen_old, fsenhik_old, fsenmin_old = st.fsen.copy(), st.fsenhik.copy(), st.fsenmin.copy()
    xs_ = np.arange(61, 71)
    tmo1 = 1. - q[xs_, 1]
    st.rsen[xs_] = rsen_old[xs_ - 1] * tmo1 + st.rsenn[xs_]
    st.hnsen[xs_, 1:3] = hnsen_old[xs_ - 1, 1:3] * tmo1[:, None] + st.hnsenn[xs_, 1:3]
    st.pshnsen[xs_] = pshnsen_old[xs_ - 1] * tmo1 + st.pshnsenn[xs_]
    st.fsennmin[np.ix_(xs_, jrest)] = st.fsenn[np.ix_(xs_, jrest)] * 0.8
    st.fsenn[np.ix_(xs_, jnk)] *= riv2[xs_, None]
    st.fsen[np.ix_(xs_, js)] = fsen_old[np.ix_(xs_ - 1, js)] * (tmo1[:, None] * riv_j[np.ix_(xs_, js)]) + st.fsenn[np.ix_(xs_, js)]
    st.fsenhik[np.ix_(xs_, j110)] = fsenhik_old[np.ix_(xs_ - 1, j110)] * (tmo1 * riv3[xs_])[:, None] + st.fsennhik[np.ix_(xs_, j110)]
    st.fsenmin[np.ix_(xs_, j110)] = fsenmin_old[np.ix_(xs_ - 1, j110)] * (tmo1 * riv4[xs_])[:, None] + st.fsennmin[np.ix_(xs_, j110)]
    st.rsen[60] = st.rsenn[60]; st.hnsen[60, 1:3] = st.hnsenn[60, 1:3]; st.pshnsen[60] = st.pshnsenn[60]
    st.fsen[60, js] = st.fsenn[60, js]
    st.fsennmin[60, jrest] = st.fsenn[60, jrest] * 0.8
    st.fsenhik[60, j110] = st.fsennhik[60, j110]
    st.fsenmin[60, js] = st.fsennmin[60, js]


# ================================================================ パート・判定補正

def fpart(ctx, st, k):
    """パート適用拡大で老齢から在職へ移す。港: emp_kyufu/siml.py:siml 274-340"""
    s = ctx.s
    if k == ctx.KIJ + 1:
        st.fpart[:] = 0.; st.fpart2[:] = 0.
    if k == ctx.partyr3:
        for x in range(60, 71):
            xrb = int(ctx.sk.xrb(YEARS.label(k) - x))
            if x <= xrb:
                continue
            r = st.r
            tmp = (r[x, :, 1] + r[x, :, 3]).sum()
            tmq = min(ctx.lpt1[k, s, x] * ctx.K.rt[k, xrb], tmp)
            if tmp > _EPS:
                tmr = r[x, :, 1] * tmq / tmp; tms = r[x, :, 3] * tmq / tmp
                r[x, :, 1] -= tmr; r[x, :, 3] -= tms
                if x < 65:
                    r[x, :, 2] += tmr; r[x, :, 4] += tms
                st.fpart[x, :, 1] += st.f[x, :, 1, 1] * tmq / tmp
                st.fpart[x, :, 2] += st.f[x, :, 3, 1] * tmq / tmp
    if ctx.flg_part >= 1 and k == ctx.partyr4:                # 適用拡大（レバー）の年度: 増分ぶんも移す
        for x in range(60, 71):
            xrb = int(ctx.sk.xrb(YEARS.label(k) - x))
            if x <= xrb:
                continue
            r = st.r
            tmp = (r[x, :, 1] + r[x, :, 3]).sum()
            lopt = ctx.lpt2[k, s, x] + ctx.lpt3[k, s, x] + ctx.lpt4[k, s, x]
            tmq = min(lopt * ctx.K.rt[k, xrb], tmp)
            if tmp > _EPS:
                tmr = r[x, :, 1] * tmq / tmp; tms = r[x, :, 3] * tmq / tmp
                r[x, :, 1] -= tmr; r[x, :, 3] -= tms
                if x < 65:
                    r[x, :, 2] += tmr; r[x, :, 4] += tms
                st.fpart2[x, :, 1] += st.f[x, :, 1, 1] * tmq / tmp
                st.fpart2[x, :, 2] += st.f[x, :, 3, 1] * tmq / tmp
    if k > ctx.partyr3:
        old = st.fpart.copy()
        xs_ = np.arange(61, 71)
        tmr = 1. - st.q2[k, xs_]
        tms = np.where(xs_ <= 67, 1. + ctx.E.hh[k], 1. + ctx.E.ci[k])
        st.fpart[xs_, :, 1:3] = old[xs_ - 1, :, 1:3] * (tmr * tms)[:, None, None]
        if ctx.flg_part >= 1 and k == ctx.partyr4:
            st.fpart[xs_, :, 1:3] += st.fpart2[xs_, :, 1:3]
        st.fpart[60, :, 1:3] = 0.


def hantei(ctx, st, k):
    """足元の実績に合わせる判定補正 rhantei / fhantei（E31 込み）。港: emp_kyufu/siml.py:siml"""
    s, xend, KIJ = ctx.s, ctx.xend, ctx.KIJ
    H = ctx.C["hantei"]
    rn, fn, routsu = st.rn, st.fn, ctx.routsu
    rh, fh = st.rhantei, st.fhantei
    q1 = ctx.K.q[k, :, 1]; q2 = st.q2[k]
    sex = "male" if s == 1 else "female"
    rcoe = H["rcoe"][sex]; radj = H["rtemp_adj"][sex]
    fcoe = {"j346": H["rcoe"][sex], "j1": H["fcoe_j1"][sex], "j14": H["fcoe_j14"][sex]}
    fadj = {"j346": H["rtemp_adj"][sex], "j1": H["ftemp_adj_j1"][sex], "j14": H["ftemp_adj_j14"][sex]}
    zero_age = H["zero_age_male"] if s == 1 else H["zero_age_female"]
    for i in (4, 3, 2, 1):
        for x in range(xend, 59, -1):
            coh = YEARS.label(k) - x
            xrb = int(ctx.sk.xrb(coh))
            xx = 0
            if x == xrb:
                if i != 1:                                   # E31
                    if i == 2:
                        rh[x, xx, i] = -(rh[x, xx, 3] + rh[x, xx, 4]) * rcoe[1]
                    else:
                        rh[x, xx, i] = rn[x, xx, i] * (routsu[s, i, 1] - 1.)
            elif i in (2, 4) and k == KIJ + 1 and 65 <= x <= 70:
                rh[x, xx, i] = rn[x, xx, i] * (routsu[s, i, 1] + radj[0 if i == 2 else 1] - 1.)
            elif i in (2, 4) and x == 65 and (k == KIJ + 2 or (s == 2 and k == KIJ + 3)):
                rh[x, xx, i] = rn[x, xx, i] * (routsu[s, i, 1] - 1.)
            else:
                rh[x, xx, i] = rh[x - 1, xx, i] * (1. - (q1[x] if i in (1, 3) else q2[x]))
            if k == KIJ + 1 and i in (1, 3) and x >= zero_age:
                rh[x, xx, i] = 0.
            if k == KIJ + 1 and i in (2, 4) and x >= 71:
                rh[x, xx, i] = 0.
            for j in (1, 3, 4, 5, 6, 14, 23):
                grp = "j1" if j == 1 else ("j14" if j == 14 else "j346")
                n = {"j346": 1, "j1": 2, "j14": 3}[grp]
                if x == xrb:
                    if i in (1, 2):
                        fh[x, xx, i, j] = -(fh[x, xx, 3, j] + fh[x, xx, 4, j]) * fcoe[grp][i - 1]
                    else:
                        fh[x, xx, i, j] = fn[x, xx, i, j] * (routsu[s, i, n] - 1.)
                elif i in (2, 4) and k == KIJ + 1 and 65 <= x <= 70:
                    fh[x, xx, i, j] = fn[x, xx, i, j] * (routsu[s, i, n] + fadj[grp][0 if i == 2 else 1] - 1.)
                elif i in (2, 4) and x == 65 and (k == KIJ + 2 or (s == 2 and k == KIJ + 3)):
                    fh[x, xx, i, j] = fn[x, xx, i, j] * (routsu[s, i, n] - 1.)
                else:
                    fh[x, xx, i, j] = fh[x - 1, xx, i, j] * (1. - (q1[x] if i in (1, 3) else q2[x]))
                if k == KIJ + 1 and i in (1, 3) and x >= zero_age:
                    fh[x, xx, i, j] = 0.
                if k == KIJ + 1 and i in (2, 4) and x >= 71:
                    fh[x, xx, i, j] = 0.


# ================================================================ 1 年度

def siml(ctx, st, k):
    """年度 k の推計（港の `siml()` 1 回ぶん）。港: emp_kyufu/siml.py:siml"""
    xend, T = ctx.xend, ctx.tend
    if k == ctx.KIJ + 1:
        st.y[:] = 0.; st.ypt[:] = 0.
        st.bbnp[:] = 0.
        g, gpt = st.g[15:xend, 0:T - 1], st.gpt[15:xend, 0:T - 1]
        with np.errstate(divide="ignore", invalid="ignore"):
            st.bbnp[15:xend, 0:T - 1] = np.where(g - gpt > _EPS, (st.bb[15:xend, 0:T - 1] * g - st.bbpt[15:xend, 0:T - 1] * gpt) / (g - gpt), 0.)
        st.gzpt[:] = 0.; st.gnpt[:] = 0.; st.gnnpt[:] = 0.; st.gd[:] = 0.
    simlg(ctx, st, k)
    simlbzw(ctx, st, k)
    for a in (st.rn, st.fn, st.fnhik, st.fnmin, st.hnn, st.pshnn, st.rsenn, st.fsenn, st.fsennhik,
              st.fsennmin, st.hnsenn, st.pshnsenn):
        a[:] = 0.
    saitesho(ctx, st, k)
    saiteizohiho(ctx, st, k)
    saiteizojuk(ctx, st, k)
    saitezai(ctx, st, k)
    saitetai(ctx, st, k)
    kyuho_move(ctx, st, k)
    simlrhnf(ctx, st, k)
    if ctx.pseid == 0 and ctx.s <= 2:
        fpart(ctx, st, k)
        if ctx.flg_hantei == 0:
            hantei(ctx, st, k)
