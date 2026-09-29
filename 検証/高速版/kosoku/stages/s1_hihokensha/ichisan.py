# -*- coding: utf-8 -*-
"""①1号・3号・未加入外（移植版 `simlichisan.c`）
=================================================
1. 実績年度: 1号を有配偶率で女有配偶・無配偶に割り、3号の女は全部有配偶。
   未加入外 = 人口（年度末） − 1号計 − 2号 − 3号計 − パート
2. 1号（任意）: 基準年度の率（59 歳以下は人口比、60 歳以上は 人口 − 2号 − パート 比）を当てる
3. 未加入外の率をコホートで送りながら `mika_soto_zero`（2040）年度へ向けて 0 に寄せる
   （係数 (2040 − 年度) / (2040 − 年度 + 1)）。21 歳以下は 0
4. 3号（男）: 基準年度の (厚年 ＋ パート) の女有配偶に対する比で延ばす
5. 3号（女有配偶）: (人口 − 2号 − パート) の比 × 男の (2号 ＋ パート) / 人口 の比で延ばし、
   制度別には男の 2号の構成比で割る。45年化のときは 45〜59 歳に補正
6. 1号（一般） = 人口 − 未加入外 − 2号 − パート − 3号計 − 1号任意（負なら 0）
7. 未加入外を 19 歳以下と上限年齢以上で 0 に、基準年度の3号も上限年齢以上を 0 に

港: hihokensha/simlichisan.py:simlichisan
仕様: §2.5、§4.2
"""
import numpy as np

from ...axis import AGES

__all__ = ["simlichisan"]

NAGE = AGES.n

_ERR = dict(divide="ignore", invalid="ignore")


def simlichisan(S, H):
    """港: hihokensha/simlichisan.py:simlichisan。仕様: §2.5"""
    hy = S.hy
    ny = hy.n
    A = S.pol.get("hihokensha.ages")
    lo, hi = A["kounen"]
    X = slice(lo, hi + 1)
    x20 = int(A["ichisan_from"])
    x_mika_min = int(A["mika_min"])
    x70 = int(A["nigou_max"]) + 1
    k0 = hy.i(S.kijunmap)
    zero_year = int(S.pol.get("hihokensha.years.mika_soto_zero"))
    jm = H.jinko_m
    ichigou, sangou, nigou = H.ichigou, H.sangou, H.nigou
    kounen, mika, iyr, xend = H.kounen, H.mika_soto, H.ichiyuhaigr, H.xend
    pn0 = H.partnin[0, 0, 0]
    r_mika = np.zeros((ny, 5, hi + 1))

    # 1. 実績年度
    Y = slice(0, k0 + 1)
    for ii in (1, 2):
        ichigou[ii, Y, 3, X] = ichigou[ii, Y, 2, X] * iyr[X]
        ichigou[ii, Y, 4, X] = ichigou[ii, Y, 2, X] * (1. - iyr[X])
    ichigou[0, Y, :, X] = ichigou[1, Y, :, X] + ichigou[2, Y, :, X]
    sangou[:, Y, 3, X] = sangou[:, Y, 2, X]
    sangou[:, Y, 4, X] = 0.
    sangou[0, Y, :, X] = sangou[1, Y, :, X] + sangou[4:7, Y, :, X].sum(0)
    mika[Y, :, X] = jm[Y, :, X] - ichigou[0, Y, :, X] - nigou[Y, :, X] - sangou[0, Y, :, X] - pn0[Y, :, X]
    with np.errstate(**_ERR):
        r_mika[Y, :, X] = mika[Y, :, X] / jm[Y, :, X]

    # 2. 1号（任意）
    X2 = slice(x20, x70)
    x60 = int(A["xend_default"])
    X2a, X2b = slice(x20, x60), slice(x60, x70)                # 59 歳以下 / 60 歳以上（港は直値の 59）
    r_ni = np.zeros((5, hi + 1))
    with np.errstate(**_ERR):
        r_ni[1:3, X2a] = ichigou[2, k0, 1:3, X2a] / jm[k0, 1:3, X2a]
        r_ni[1:3, X2b] = ichigou[2, k0, 1:3, X2b] / (jm[k0, 1:3, X2b] - nigou[k0, 1:3, X2b] - pn0[k0, 1:3, X2b])
    Y = slice(k0 + 1, ny - 1)
    ichigou[2, Y, 1:3, X2a] = jm[Y, 1:3, X2a] * r_ni[1:3, X2a]
    ichigou[2, Y, 1:3, X2b] = (jm[Y, 1:3, X2b] - nigou[Y, 1:3, X2b] - pn0[Y, 1:3, X2b]) * r_ni[1:3, X2b]
    with np.errstate(**_ERR):
        ichigou[2, Y, 3, X2] = (ichigou[2, Y, 2, X2] * iyr[X2] * (jm[Y, 3, X2] / jm[Y, 2, X2])
                                / (jm[k0, 3, X2] / jm[k0, 2, X2]))
    ichigou[2, Y, 4, X2] = ichigou[2, Y, 2, X2] - ichigou[2, Y, 3, X2]
    ichigou[2, Y, 0, X2] = ichigou[2, Y, 1, X2] + ichigou[2, Y, 2, X2]

    # 3. 未加入外（20〜64 歳）。率はコホートで送る（年度の漸化式）
    x65 = 65                                             # 港: range(20, 65)
    for y in range(k0 + 1, ny):
        nendo = hy.label(y)
        keisu = 0. if nendo >= zero_year else (zero_year - nendo) / (zero_year - nendo + 1)
        r_mika[y, 1:3, x20:x_mika_min] = 0.
        r_mika[y, 1:3, x_mika_min:x65] = r_mika[y - 1, 1:3, x_mika_min - 1:x65 - 1] * keisu
    Y = slice(k0 + 1, ny)
    X3 = slice(x20, x65)
    mika[Y, 1:3, X3] = jm[Y, 1:3, X3] * r_mika[Y, 1:3, X3]
    ys = np.arange(k0 + 1, ny)[:, None]
    xs = np.arange(x20, x65)[None, :]
    d = ys - k0
    b = np.clip(xs - d, 0, hi)                          # 基準年度で対応する年齢
    with np.errstate(**_ERR):
        ratio = jm[Y, 4, X3] / jm[Y, 2, X3]
        via = (mika[Y, 2, X3] * (mika[k0, 4][b] / mika[k0, 2][b]) * ratio / (jm[k0, 4][b] / jm[k0, 2][b]))
        plain = mika[Y, 2, X3] * ratio
    mika[Y, 4, X3] = np.where(xs - d > x20, via, plain)
    mika[Y, 3, X3] = mika[Y, 2, X3] - mika[Y, 4, X3]
    mika[Y, 0, X3] = mika[Y, 1, X3] + mika[Y, 2, X3]

    # 4. 3号（男）: 20 歳〜上限年齢の手前
    xs_all = np.arange(NAGE)[None, :]
    inx = (xs_all >= x20) & (xs_all < xend[Y, None])     # (ny−k0−1, NAGE)
    den = kounen[1, k0, 3] + pn0[k0, 3]
    with np.errstate(**_ERR):
        s1 = np.where(den > 0., sangou[1, k0, 1] * (kounen[1, Y, 3] + pn0[Y, 3]) / den, 0.)
    sangou[1, Y, 1] = np.where(inx, s1, sangou[1, Y, 1])
    sangou[3, Y, 1] = np.where(inx, 0., sangou[3, Y, 1])
    sangou[2, Y, 1] = np.where(inx, sangou[1, Y, 1], sangou[2, Y, 1])
    for seido in (4, 5, 6):
        with np.errstate(**_ERR):
            v = np.where(kounen[seido, k0, 3] > 0., sangou[seido, k0, 1] * kounen[seido, Y, 3] / kounen[seido, k0, 3], 0.)
        sangou[seido, Y, 1] = np.where(inx, v, sangou[seido, Y, 1])
    sangou[0, Y, 1] = np.where(inx, sangou[1, Y, 1] + sangou[4:7, Y, 1].sum(0), sangou[0, Y, 1])

    # 5. 3号（女有配偶）
    tmp = jm[k0, 3] - nigou[k0, 3] - pn0[k0, 3]
    tmq = jm[Y, 3] - nigou[Y, 3] - pn0[Y, 3]
    with np.errstate(**_ERR):
        s03 = np.where((tmp > 0.) & (tmq > 0.),
                       sangou[0, k0, 3] * tmq / tmp * ((nigou[Y, 1] + pn0[Y, 1]) / jm[Y, 1])
                       / ((nigou[k0, 1] + pn0[k0, 1]) / jm[k0, 1]), 0.)
    s03 = np.where(inx, s03, sangou[0, Y, 3])
    sangou[0, Y, 3] = s03
    sangou[0, Y, 4] = np.where(inx, 0., sangou[0, Y, 4])
    sangou[0, Y, 2] = np.where(inx, s03, sangou[0, Y, 2])
    den1 = nigou[Y, 1] + pn0[Y, 1]
    with np.errstate(**_ERR):
        s13 = s03 * (kounen[1, Y, 1] + pn0[Y, 1]) / den1
        s33 = s03 * kounen[3, Y, 1] / den1
    sangou[1, Y, 3] = np.where(inx, s13, sangou[1, Y, 3])
    sangou[1, Y, 4] = np.where(inx, 0., sangou[1, Y, 4])
    sangou[1, Y, 2] = np.where(inx, s13, sangou[1, Y, 2])
    sangou[3, Y, 3] = np.where(inx, s33, sangou[3, Y, 3])
    sangou[3, Y, 4] = np.where(inx, 0., sangou[3, Y, 4])
    sangou[3, Y, 2] = np.where(inx, s33, sangou[3, Y, 2])
    sangou[2, Y, 2:5] = np.where(inx[:, None], sangou[1, Y, 2:5] - sangou[3, Y, 2:5], sangou[2, Y, 2:5])
    for seido in (4, 5, 6):
        with np.errstate(**_ERR):
            v = s03 * kounen[seido, Y, 1] / den1
        sangou[seido, Y, 3] = np.where(inx, v, sangou[seido, Y, 3])
        sangou[seido, Y, 4] = np.where(inx, 0., sangou[seido, Y, 4])
        sangou[seido, Y, 2] = np.where(inx, v, sangou[seido, Y, 2])
    if S.mode45 == 1:
        # 45年化: 45〜59 歳の3号（性 1〜3）に 1 + (XEND − 60)/5 × 係数 を掛ける
        hosei = {int(k): float(v) for k, v in S.pol.get("hihokensha.ichisan.mode45_hosei").items()}
        base = int(A["xend_default"])
        fac = np.ones((ny - k0 - 1, NAGE))
        for a0, coef in hosei.items():
            fac[:, a0:a0 + 5] = 1. + (xend[Y, None] - base) / 5. * coef
        sangou[:, Y, 1:4] *= np.where(inx, fac, 1.)[None, :, None, :]
    sangou[:, Y, 0] = np.where(inx[None], sangou[:, Y, 1] + sangou[:, Y, 2], sangou[:, Y, 0])

    # 6. 1号（一般）
    Y = slice(k0 + 1, ny - 1)
    inx6 = inx[:-1]
    tmp = (jm[Y, 1:5] - mika[Y, 1:5] - nigou[Y, 1:5] - pn0[Y, 1:5] - sangou[0, Y, 1:5] - ichigou[2, Y, 1:5])
    neg = (tmp < 0.) & inx6[:, None]
    if neg.any():
        H.notes.append("1号一般がマイナス（0 に切った）: %d 箇所" % int(neg.sum()))
    ichigou[1, Y, 1:5] = np.where(inx6[:, None], np.maximum(tmp, 0.), ichigou[1, Y, 1:5])
    ichigou[1, Y, 2] = np.where(inx6, ichigou[1, Y, 3] + ichigou[1, Y, 4], ichigou[1, Y, 2])
    ichigou[1, Y, 0] = np.where(inx6, ichigou[1, Y, 1] + ichigou[1, Y, 2], ichigou[1, Y, 0])
    ichigou[0, Y, :, X2] = ichigou[1, Y, :, X2] + ichigou[2, Y, :, X2]

    # 7. 端の年齢を 0 に
    mika[:, :, :x20] = 0.
    out = xs_all >= xend[:, None]                        # (ny, NAGE)
    mika[...] = np.where(out[:, None, :], 0., mika)
    sangou[:, k0, :, xend[k0]:] = 0.
