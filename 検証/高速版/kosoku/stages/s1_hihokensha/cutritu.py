# -*- coding: utf-8 -*-
"""①マクロ経済スライドの調整率（移植版 `cutout.c`）
====================================================
1. 公的年金の被保険者数 `kouteki[y]` = 厚年 ＋ パート（69 歳以下）＋ 共済 3 制度 ＋ 3号計 ＋ 1号（一般）
   （20 歳〜上限年齢の手前）＋ 1号（任意）（20〜69 歳）。男女、15〜110 歳
2. 年央の被保険者数 `kouteki_cent`: 実績年度（2020〜2022）は公表値（yaml
   `hihokensha.cutritu.kouteki_cent_actual`）、以降は前年度と当年度の平均
3. 率[年度] = ((2 年前 − TMQ) / (5 年前 − TMP))^(1/3) × `jyumyo`（0.997。平均余命の伸び）。
   TMP/TMQ は 45年化のときに 60 歳以上の 1号・3号を除くぶん
4. 1 を超えたら 1。書く値は 1 / 率 − 1 を小数 4 桁に（率は 6 桁に）丸めたもの

港: hihokensha/cutout.py:cutout
仕様: §5.7、§11 ①
"""
import numpy as np

__all__ = ["raund", "cutritu"]


def raund(a, n):
    """港 `stdfm.c` の `raund`: 0 から遠い方へ丸める（小数 n 桁）。0 は +0。
    港: hihokensha/cnum.py:raund"""
    s = 10. ** n
    v = np.asarray(a, dtype=np.float64) * s
    d = np.where(v > 0., np.floor(v + 0.5), np.ceil(v - 0.5))
    return d / s + 0.


def cutritu(S, H):
    """調整率を作る → (率 `cy` の軸, 書く値 1/率 − 1)。港: hihokensha/cutout.py:cutout。仕様: §5.7"""
    hy, cy = S.hy, S.cy
    ny = hy.n
    C = S.pol.get("hihokensha.cutritu")
    A = S.pol.get("hihokensha.ages")
    lo, hi = A["cutritu_sum"]
    x20, x70 = int(A["ichisan_from"]), int(A["nigou_max"]) + 1
    kounen, ichigou, sangou, xend = H.kounen, H.ichigou, H.sangou, H.xend
    pn0 = H.partnin[0, 0, 0]
    x = np.arange(hi + 1)[None, :]
    m70 = x < x70
    m20x = (x >= x20) & (x < xend[:, None])
    m2069 = (x >= x20) & (x < x70)
    a = np.where(m70, kounen[1, :, 1:3, :hi + 1].sum(1) + pn0[:, 1:3, :hi + 1].sum(1), 0.)
    a += kounen[4:7, :, 1:3, :hi + 1].sum((0, 2))
    a += np.where(m20x, sangou[0, :, 1:3, :hi + 1].sum(1) + ichigou[1, :, 1:3, :hi + 1].sum(1), 0.)
    a += np.where(m2069, ichigou[2, :, 1:3, :hi + 1].sum(1), 0.)
    kouteki = a[:, lo:hi + 1].sum(1)
    cent = np.zeros(ny)
    actual = {int(k): float(v) for k, v in C["kouteki_cent_actual"].items()}
    for y, v in actual.items():
        cent[hy.i(y)] = v
    y0 = hy.i(max(actual)) + 1
    cent[y0:] = (kouteki[y0 - 1:-1] + kouteki[y0:]) / 2.
    lag_r, lag_o = int(C["lag_recent"]), int(C["lag_old"])
    idx = np.arange(hy.i(S.cut_jy + 1), ny)
    old = cent[idx - lag_o]
    if not (old > 0.).all():
        bad = hy.label(int(idx[np.argmin(old > 0.)]) - lag_o)
        raise ValueError("%d 年度の公的年金被保険者数が正しくない" % bad)
    # 45年化: 60 歳〜上限年齢の 1号（一般）・3号は被保険者数から除く（TMP: 5〜6 年前、TMQ: 2〜3 年前の年央）
    tmp = np.zeros(ny); tmq = np.zeros(ny)
    if S.mode45 == 1:
        x60 = int(A["xend_default"])
        for y in idx:
            te = int(xend[y - 2])
            if te > x60 and y - lag_o - 1 >= 0:
                a = ichigou[1, :, 0, x60:te] + sangou[0, :, 0, x60:te]
                tmp[y] = (a[y - lag_o - 1].sum() + a[y - lag_o].sum()) / 2.
                tmq[y] = (a[y - lag_r - 1].sum() + a[y - lag_r].sum()) / 2.
    cut = H.cutritu.copy()
    cut[cy.i(S.cut_jy) + 1:] = ((cent[idx - lag_r] - tmq[idx]) / (old - tmp[idx])) ** (1. / float(C["root"])) * float(C["jyumyo"])
    cut = np.minimum(cut, 1.)
    cut2 = 1. / cut - 1.
    cut = raund(cut, int(C["digits"]))
    cut2 = raund(cut2, int(C["digits2"]))
    return cut, cut2
