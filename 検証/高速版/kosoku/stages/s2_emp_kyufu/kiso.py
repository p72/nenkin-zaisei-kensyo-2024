# -*- coding: utf-8 -*-
"""②の基礎率（`kiso.cpp`）— 基準年度の値を将来年度へ伸ばす
============================================================
種別 `s`（1 男 / 2 女 / 3 男女計＝厚年の3号）ごとに `Kisor`（基準年度の値）から

    q[k, x, i]      受給者の失権率（1 老齢 / 2 障害 / 3 遺族）。生命表 `qp` の改善で伸ばす
    u[k, x, i]      被保険者の脱退力（0 計 / 1 生存 / 2 障害 / 3 死亡）
    rt[k, x]        再加入者 /（新規加入者＋再加入者）
    yx[k, x, j]     年齢相関（0 配偶者 / 1 子）、ns[k, x]
    rc[k, x]        有子割合（女は 1959 年度生以降を年度ごとに伸ばす）
    cl[k, i] cl2    障害の等級別割合
    kd[k, i, j, x]  加給対象者割合・振替加算割合
    ikucoe / jiiku  育休産休取得率・標準報酬比率

港の癖で残すもの（`検証/原本の不具合.md`）: E23 — 厚年の死亡脱退力の分母だけ 2021 年
1年ぶん（共済は 2019〜2021 の3年平均）。yaml `kounen.kiso.u_qp_base_kou` で明示する。

港: emp_kyufu/kiso.py:kiso
仕様: §5.5（基礎率）
"""
from dataclasses import dataclass

import numpy as np

from ...axis import YEARS
from .inputs import NX
from .seid import cohort_idx

__all__ = ["KisoRates", "kiso_rates"]


@dataclass
class KisoRates:
    q: np.ndarray             # (YEARS.n, NX, 4)
    u: np.ndarray             # (YEARS.n, NX, 4)
    rt: np.ndarray            # (YEARS.n, NX)
    yx: np.ndarray            # (YEARS.n, NX, 2)
    ns: np.ndarray            # (YEARS.n, NX)
    rc: np.ndarray            # (YEARS.n, NX)
    cl: np.ndarray            # (YEARS.n, 4)
    cl2: np.ndarray
    kd: np.ndarray            # (YEARS.n, 7, 5, NX)
    ikucoe: np.ndarray        # (YEARS.n, NX)
    jiiku: np.ndarray


def _by_age(points):
    x = np.arange(NX)
    out = np.zeros(NX)
    for key, val in sorted((int(k), v) for k, v in points.items()):
        out[x >= key] = float(val)
    return out


def _growth_factor(pol, k, x):
    """女の有子割合・加給対象者割合の年度ごとの伸び（`rc_growth`）。x は配列。"""
    G = pol.get("kounen.kiso.rc_growth")
    n = float(YEARS.label(k) - G["base_year"])             # 基準年度からの年数（(n+1)/n で線形に伸びる）
    coh = YEARS.label(k) - x
    f = np.ones(x.shape)
    f[coh == G["cohort"]] = (n + 0.5) / n                  # 境の生年度は半年ぶん
    f[coh < G["cohort"]] = (n + 1.) / n
    return f


def kiso_rates(pol, kr, qp, pseid, s, sk, flg_inout=0):
    """`kr`: `Kisor`、`qp[k, x, ss]` 生命表、`sk`: `ShikyuKaishi`（支給開始年齢）。"""
    K = pol.get("kounen.kiso")
    KS = YEARS.i(pol.get("kounen.years.kijun")) - 1
    KE = YEARS.n - 1
    seiy = YEARS.i(pol.get("kounen.flags.seiy"))
    ss = 2 if s == 2 else 1
    qb = [YEARS.i(int(y)) for y in K["qp_base_years"]]
    qp0 = qp[qb].mean(axis=0)                              # (x, ss) 3年平均
    kk = np.minimum(np.arange(YEARS.n), seiy)
    x = np.arange(NX)

    # ---- Q ----
    q = np.zeros((YEARS.n, NX, 4))
    q[KS] = kr.q
    if pseid != 0 and ss == 2:
        q[KS, 20:55, 3] = qp0[20:55, 1]
    for i in (1, 3, 2):                                    # 2 は 1 を使うので後
        sss = (3 - ss) if i == 3 else ss
        base = q[KS, :, i]
        pos = base > 0.
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = np.where(qp0[:, sss] > 0., qp[kk][:, :, sss] / qp0[:, sss], 0.)     # (k, x)
        for k in range(KS + 1, KE + 1):
            v = np.zeros(NX)
            if i != 2:
                v[:105] = base[:105] * ratio[k, :105]
                if i == 3:
                    v[:60] = base[:60]
                if base[104] > 1.0e-6:
                    v[105:] = np.minimum(1., v[104] * base[105:] / base[104])
            else:
                b1 = q[KS, :, 1]
                ok = b1 > 1.0e-6
                v[ok] = np.minimum(1., base[ok] * q[k, ok, 1] / b1[ok])
            v = np.where(pos, v, 0.)
            v = np.minimum(1., np.maximum(0., v))
            v[115] = 1.
            if i == 3:
                v[19] = 1.
            q[k, :, i] = v
    ny = int(K["shogai65_years"])
    for k in range(KS + 1, KE + 1):
        q[k, 65, 2] = (q[k, 65, 2] * max(0., (KS + ny - k) / float(ny))
                       + (q[k, 64, 2] + q[k, 66, 2]) / 2. * min(1., (k - KS) / float(ny)))

    # ---- U ----
    u = np.zeros((YEARS.n, NX, 4))
    u[KS + 1] = kr.u
    xr = slice(15, 85)
    rds_end = YEARS.i(K["rds_end_year"])
    with np.errstate(divide="ignore", invalid="ignore"):
        if pseid == 0:
            # 労働参加のシナリオ（flg_inout = 労働力率 − 1）。2（現状）は港が rds を 0 のまま置く（縮小しない）
            tbl = K["rds"].get("inout%d" % flg_inout)
            rds = _by_age(tbl["male" if ss == 1 else "female"]) if tbl is not None else np.zeros(NX)
            u_qb = YEARS.i(K["u_qp_base_kou"])                     # E23: 1年ぶん
            for k in range(KS + 1, KE + 1):
                if KS + 1 < k <= rds_end:
                    u[k, xr, 1] = u[KS + 1, xr, 1] * (1. - rds[xr] * (k - (KS + 1.)) / (rds_end - (KS + 1.)))
                elif k > rds_end:
                    u[k, xr, 1] = u[rds_end, xr, 1]
                u[k, xr, 3] = u[KS + 1, xr, 3] * qp[kk[k], xr, ss] / qp[u_qb, xr, ss]
                _death_from_q(u, q, k, 70, 85)
        elif pseid in (1, 4):
            u[KS + 1, xr, 0] = u[KS + 1, xr, 1] + u[KS + 1, xr, 2] + u[KS + 1, xr, 3]
            SH = K["kyosai_shift"]
            tmp = float(SH["kok" if pseid == 1 else "ren"][str(s)])
            y64, y65, y66 = (YEARS.i(SH["from_64"]), [YEARS.i(int(v)) for v in SH["at_65"]], YEARS.i(SH["from_66"]))
            for k in range(KS + 1, KE + 1):
                u[k, xr, 0] = u[KS + 1, xr, 0]
                if k >= y64:
                    u[k, 64, 0] = u[KS + 1, 64, 0] - tmp
                if k in y65:
                    u[k, 65, 0] = u[KS + 1, 65, 0] + tmp
                if k >= y66:
                    u[k, 66, 0] = u[KS + 1, 66, 0] + tmp
                u[k, xr, 3] = u[KS + 1, xr, 3] * qp[kk[k], xr, ss] / qp0[xr, ss]
                _death_from_q(u, q, k, 70, 85)
                u[k, xr, 0] += u[k, xr, 3] - u[KS + 1, xr, 3]
        else:
            u[KS + 1, xr, 0] = u[KS + 1, xr, 1] + u[KS + 1, xr, 2] + u[KS + 1, xr, 3]
            xr5 = slice(15, 86)
            for k in range(KS + 1, KE + 1):
                u[k, xr5, 3] = u[KS + 1, xr5, 3] * qp[kk[k], xr5, ss] / qp0[xr5, ss]
                _death_from_q(u, q, k, 70, 86)
                u[k, xr5, 1] = u[KS + 1, xr5, 0] - u[KS + 1, xr5, 2] - u[KS + 1, xr5, 3]
    for k in range(KS + 1, KE + 1):
        u[k, 15:65, 2] = u[KS + 1, 15:65, 2]
        u[k, 65:85, 2] = 0.
        xrb = np.maximum(60, sk.xrb(YEARS.label(k) - x[xr]))
        over = x[xr] > xrb
        if pseid in (0, 5):
            u[k, xr, 1][over] = 0.
        else:
            u[k, xr, 0][over] = (u[k, xr, 2] + u[k, xr, 3])[over]
    tmxend = 85 if pseid == 0 else 70
    xr5 = slice(15, 86)
    hi = x[xr5] >= tmxend
    for k in range(KS + 1, KE + 1):
        if pseid == 0:
            u[k, xr5, 1][hi] = 1.
        elif pseid in (1, 4):
            u[k, xr5, 0][hi] = 1000.
        else:
            u[k, xr5, 1][hi] = 1000.
        if pseid in (0, 5):
            u[k, xr5, 0] = u[k, xr5, 1] + u[k, xr5, 2] + u[k, xr5, 3]
        u[k, xr5, 0] = np.maximum(0., u[k, xr5, 0])
        u[k, xr5, 2] = np.minimum(1., np.maximum(0., u[k, xr5, 2]))
        u[k, xr5, 3] = np.minimum(np.maximum(0., u[k, xr5, 3]), 1. - u[k, xr5, 2])
        u[k, xr5, 1] = u[k, xr5, 0] - u[k, xr5, 2] - u[k, xr5, 3]

    # ---- RT ----
    rt = np.zeros((YEARS.n, NX))
    rt[KS + 1] = kr.rt
    for k in range(KS + 2, KE + 1):
        rt[k, 15:75] = kr.rt[15:75]
        xrb = np.maximum(60, sk.xrb(YEARS.label(k) - x[15:75]))
        rt[k, 15:75][x[15:75] > xrb] = 0.

    # ---- YX / NS / RC / CL ----
    yx = np.zeros((YEARS.n, NX, 2)); ns = np.zeros((YEARS.n, NX)); rc = np.zeros((YEARS.n, NX))
    yx[KS:] = kr.yx; ns[KS:] = kr.ns; rc[KS:] = kr.rc
    if s == 2:
        for k in range(KS + 1, KE + 1):
            rc[k, 58:] = rc[k - 1, 58:] * _growth_factor(pol, k, x[58:])
    cl = np.zeros((YEARS.n, 4)); cl2 = np.zeros((YEARS.n, 4))
    cl[KS:] = kr.cl; cl2[KS:] = kr.cl2

    # ---- KD ----
    kd = np.zeros((YEARS.n, 7, 5, NX))
    r = kr.kd_raw
    kd[KS, 1, 1] = r[:, 0]; kd[KS, 2, 1] = r[:, 1]
    kd[KS, 1, 2] = r[:, 2]; kd[KS, 1, 3] = r[:, 3]
    kd[KS, 3, 1] = r[:, 4]; kd[KS, 4, 1] = r[:, 5]
    kd[KS, 3, 2] = r[:, 6]; kd[KS, 3, 3] = r[:, 7]
    kd[KS, 5, 2] = r[:, 8]; kd[KS, 5, 3] = r[:, 9]
    kd[KS, 1, 4] = r[:, 10]
    kd[KS, 2, 2:4] = kd[KS, 1, 2:4]; kd[KS, 4, 2:4] = kd[KS, 3, 2:4]; kd[KS, 3, 4] = kd[KS, 1, 4]
    FK = K["furikae"]
    kdc = float(FK["kdc"][0 if s != 2 else 1])
    for k in range(KS, KE + 1):
        kd[k, 1:6] = kd[KS, 1:6]
        steps = np.clip(YEARS.label(k) - x - (FK["cohort_start"] - 1), 0, FK["steps"])
        kd[k, 6, 1:5] = kd[KS, 1, 1:5] * (kdc * steps)
    kd[:, 2, 4] = 0.; kd[:, 4, 4] = 0.; kd[:, 5, 4] = 0.; kd[:, 5, 1] = 0.
    if s == 2:
        for k in range(KS + 1, KE + 1):
            f = _growth_factor(pol, k, x[58:])
            kd[k, 5, 2, 58:] = kd[k - 1, 5, 2, 58:] * f
            kd[k, 5, 3, 58:] = kd[k - 1, 5, 3, 58:] * f

    ikucoe = np.zeros((YEARS.n, NX)); jiiku = np.zeros((YEARS.n, NX))
    ikucoe[KS + 1:] = kr.ikucoe; jiiku[KS + 1:] = kr.jiiku
    return KisoRates(q, u, rt, yx, ns, rc, cl, cl2, kd, ikucoe, jiiku)


def _death_from_q(u, q, k, x0, x1):
    """70歳以上の死亡脱退力は老齢の失権率から `−log(1 − q)`（q が 1 に近ければ 1000）。"""
    qq = q[k, x0:x1, 1]
    with np.errstate(divide="ignore"):
        u[k, x0:x1, 3] = np.where(qq < 1. - 1.0e-6, -np.log(np.maximum(1. - qq, 1e-300)), 1000.)
