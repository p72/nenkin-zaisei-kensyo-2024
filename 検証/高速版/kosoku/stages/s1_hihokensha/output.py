# -*- coding: utf-8 -*-
"""①の出力（移植版 `fout.c` `cutout.c` の書き手）
=================================================
58 の分類（yaml `hihokensha.classes.names`。港の `waku-00..57`）を (分類, 年度, 性, 年齢) の表にし、
`Waku` に置く。港の配置の CSV も書けるので、下流（②③④⑤）の読み手がそのまま読める。

分類の作り方（港 `fout.c:37-440` の switch。どれも要素ごとの選択と足し引き）
     0 公的計 = 1号計 ＋ 2号 ＋ 3号計 ＋ パート
     1 被用者計 = 厚年・共済の計 ＋ パート（70 歳以上は厚年を除く）
     2 国年2号 = 被用者計の 64 歳以下
     3/4 旧厚 70 歳未満（パート込み）/ 70 歳以上     5/6 旧厚12種 / 3種    7 パート
     8〜10 共済 2号   11〜13 1号計 / 一般 / 任意   14〜18 3号計 / 旧厚 / 共済 3 つ
    19 未加入外（70 歳未満）   20/21 人口 年央 / 年度末
    22〜25 適用拡大（現行）の計 / 元1号 / 元3号 / 元その他
    26〜41 1段階目の増分（ykubun 2 − 1）、42〜57 2段階目の増分（3 − 2）（yaml `part_diff`）

年齢は 15〜120 歳を作り、101 歳以上は 100 歳に寄せる（港の `-NN.csv` の 100 の列）。年度は
ks〜kf を `YEARS` に写す。書かない出力: `-nenreikei`（年齢計。`count` の和で出る）、`-nenkeikan`
（年度間。港は未初期化読み H1）、`-settei`、`-err`、`wakuroud-*`、`-roudkei`（労働力の参考出力）。

港: hihokensha/fout.py:fout
港: hihokensha/cutout.py:cutout
仕様: §2、§12.4
"""
import os

import numpy as np

from ...axis import YEARS, AGES
from ...contracts import Waku, SEXES
from .cutritu import raund

__all__ = ["NB", "class_table", "to_waku", "to_port_csv"]

NB = 58


def class_table(S, H):
    """(分類, `YEARS`, 性, 年齢) の表。年度 ks〜kf、年齢 15〜120 歳に値があり、それ以外は 0。
    港: hihokensha/fout.py:fout。仕様: §2"""
    hy = S.hy
    C = S.pol.get("hihokensha.classes")
    A = S.pol.get("hihokensha.ages")
    lo, hi = A["fout"]
    X = slice(lo, hi + 1)
    x70 = int(A["nigou_max"]) + 1
    x65 = int(A["kokunen_nigou_max"]) + 1
    Yh = hy.s(S.ks, S.kf)                                 # hy の添字
    Yo = YEARS.s(S.ks, S.kf)                              # YEARS の添字
    ig, sg, ng = H.ichigou[:, Yh], H.sangou[:, Yh], H.nigou[Yh]
    kn, mika, jc, jm = H.kounen[:, Yh], H.mika_soto[Yh], H.jinko_c[Yh], H.jinko_m[Yh]
    pn = H.partnin[:, :, :, Yh]
    pn0 = pn[0, 0, 0]
    T = np.zeros((NB, YEARS.n, len(SEXES), AGES.n))
    T[0, Yo, :, X] = ig[0, :, :, X] + ng[:, :, X] + sg[0, :, :, X] + pn0[:, :, X]
    if S.mode45 == 1:                                     # 45年化: 上限年齢以上は 1号（任意）＋ 2号 ＋ パート
        xe = H.xend[Yh]
        over = (np.arange(AGES.n)[None, :] >= xe[:, None]) & (np.arange(AGES.n)[None, :] >= lo)
        T[0, Yo] = np.where(over[:, None, :], ig[2] + ng + pn0, T[0, Yo])
    T[1, Yo, :, X] = kn[0, :, :, X] + pn0[:, :, X]
    T[1, Yo, :, x70:hi + 1] -= kn[1, :, :, x70:hi + 1]
    T[2, Yo, :, lo:x65] = kn[0, :, :, lo:x65] + pn0[:, :, lo:x65]
    T[3, Yo, :, lo:x70] = kn[1, :, :, lo:x70] + pn0[:, :, lo:x70]
    T[4, Yo, :, x70:hi + 1] = kn[1, :, :, x70:hi + 1]
    T[5, Yo, :, X] = kn[2, :, :, X]
    T[6, Yo, :, X] = kn[3, :, :, X]
    T[7, Yo, :, X] = pn0[:, :, X]
    for b in (8, 9, 10):
        T[b, Yo, :, X] = kn[b - 4, :, :, X]
    for b in (11, 12, 13):
        T[b, Yo, :, X] = ig[b - 11, :, :, X]
    T[14, Yo, :, X] = sg[0, :, :, X]
    T[15, Yo, :, X] = sg[1, :, :, X]
    for b in (16, 17, 18):
        T[b, Yo, :, X] = sg[b - 12, :, :, X]
    T[19, Yo, :, lo:x70] = mika[:, :, lo:x70]
    T[20, Yo, :, X] = jc[:, :, X]
    T[21, Yo, :, X] = jm[:, :, X]
    for b, p in zip((22, 23, 24, 25), C["part_base"]):
        T[b, Yo, :, X] = pn[int(p), 0, 1, :, :, X]
    years = hy.labels()[Yh]
    on1 = (S.part >= 1) & (years >= S.partyr1)
    on2 = (S.part == 2) & (years >= S.partyr2)
    for b, (p, t, stage) in C["part_diff"].items():
        b, p, t = int(b), int(p), int(t)
        on = on1 if int(stage) == 1 else on2
        if not on.any():
            continue
        yk = 2 if int(stage) == 1 else 3
        T[b, Yo, :, X] = np.where(on[:, None, None], pn[p, t, yk, :, :, X] - pn[p, t, yk - 1, :, :, X], 0.)
    # 101 歳以上を 100 歳に寄せる
    top = int(A["fout_fold"])
    T[:, :, :, top] += T[:, :, :, top + 1:].sum(-1)
    T[:, :, :, top + 1:] = 0.
    return T


def to_waku(S, T, cut2, prov):
    """分類の表と調整率を `Waku` に。"""
    C = S.pol.get("hihokensha.classes")
    names = tuple(C["names"][str(i)] for i in range(NB))
    cut = YEARS.zeros()
    for y in range(S.cnendo, S.kf + 1):
        cut[YEARS.i(y)] = cut2[S.cy.i(y)]
    return Waku(prov=prov, classes=names, count=T, cutritu=cut)


def to_port_csv(run, case, outdir):
    """港の配置で `waku{case}-00..57.csv` と `waku{case}-m.csv` を書く → {"waku": [58 本], "m": path}。
    人数は港と同じく整数に丸める（0 から遠い方へ）。港: hihokensha/fout.py:fout"""
    S = run.S
    os.makedirs(outdir, exist_ok=True)
    F = run.out.count
    lo, _ = S.pol.get("hihokensha.ages.fout")
    top = int(S.pol.get("hihokensha.ages.fout_fold"))
    ncol = top - lo + 2                                    # 計 ＋ lo〜top 歳
    fmt = ",".join(["%d.000000"] * ncol)
    head = "試算番号, BANGO=, %s\n分類,性,年度,計,%s,%d\n" % (case, ",".join("%02d" % a for a in range(lo, top)), top)
    ys = range(S.ks, S.kf + 1)
    paths = []
    for b in range(NB):
        out = [head]
        for s in range(len(SEXES)):
            for y in ys:
                v = F[b, YEARS.i(y), s, lo:top + 1]
                row = np.concatenate([[v.sum()], v])
                r = raund(row, 0).astype(np.int64)
                out.append("%4d,%1d,%4d," % (b, s, y) + fmt % tuple(r) + "\n")
        p = os.path.join(outdir, "waku%s-%02d.csv" % (case, b))
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write("".join(out))
        paths.append(p)
    pm = os.path.join(outdir, "waku%s-m.csv" % case)
    with open(pm, "w", encoding="utf-8", newline="") as f:
        f.write("".join("%4d,%7.6f\n" % (y, run.out.cutritu[YEARS.i(y)]) for y in range(S.cnendo, S.kf + 1)))
    return {"waku": paths, "m": pm}
