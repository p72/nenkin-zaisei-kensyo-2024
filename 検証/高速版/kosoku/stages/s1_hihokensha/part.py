# -*- coding: utf-8 -*-
"""①適用拡大（パート）の人数（移植版 `simlpart.c`）
=====================================================
`partnin[pkubun, tkubun, ykubun, y, s, x]` を作り、そのぶんを 1号・3号から差し引き、被用者数と
総労働時間に足し込む。添字は yaml `hihokensha.part`（pkubun 元制度、tkubun 時間区分、
ykubun 0 累積 / 1 現行 / 2 1段階目 / 3 2段階目）。港は (y, s, x, p, t, yk) の順だが、高速版は
(p, t, yk) を先に置いて年度・性・年齢の面を連続にする（`partnin[0, 0, 0]` が現行のパート計）。
ykubun の軸は段階数ぶんだけ（`Settings.part` = 0 なら 0 と 1 の 2 つ）。

 1. 年齢区分別（5 歳きざみ `kubun` 1〜15）の短時間雇用者数 `ktj`
      [1] = 雇用者区分 4+5（週 20〜29 時間）、[2] = 1+2+6（週 30 時間以上）、[3] = 3（週 20 時間未満）
 2. 基礎数値 `kbetu_partkiso`（`partkyr` 年度）を短時間雇用者数の伸びで延ばす → `kbn`。
    20〜59 歳は「元その他」を「元1号」に、週 20〜30 時間は「元3号」を「元1号」に寄せる
 3. 元制度の人数（年齢区分の 5 歳計）で頭を打ち、年齢別の割合 `pw` を作る
 4. 年齢別: 15〜19 歳は元その他、20〜59 歳は元1号（一般）・元3号（制度別）、60〜69 歳は元1号（任意）と
    元その他。差し引きは当年度の段階（ykubun）のぶんだけ
 5. 合計（pkubun 0、tkubun 0）を作り、累積（ykubun 0）に足す
 6. `tashikomi`: 被用者数（`koyou_j_*[7, 9, 10]`）と総労働時間（`soroudh_*[7, 8, 9]`）に足し込む。
    年央は前年度と当年度の半分ずつ（最初の年度は当年度の半分だけ = 10 月からの適用）
 7. 被用者の平均労働時間と、1号計・3号計の作り直し

45年化（`mode45 = 1`）は 60 歳〜上限年齢の手前を年度・年齢ごとに配り直す（`_mode45_part`。港も未検証の枝）。

港: hihokensha/simlpart.py:simlpart, tashikomi
仕様: §2.4、§11 ①
"""
import numpy as np

from ...axis import AGES

__all__ = ["ykubun", "simlpart", "tashikomi"]

NAGE = AGES.n
_ERR = dict(divide="ignore", invalid="ignore")


def ykubun(nendo, S):
    """年度がどの段階か: 1 現行 / 2 1段階目（partyr1〜）/ 3 2段階目（partyr2〜）。配列も可。
    港: hihokensha/simlpart.py:simlpart"""
    n = np.asarray(nendo)
    return np.where(n < S.partyr1, 1, np.where(n < S.partyr2, 2, 3))


def _pick(a, yk, axis=0):
    """`a` の軸 `axis` が ykubun 1〜、その次が年度。年度ごとの段階を選ぶ → `a[…, yk[y]−1, y, …]`。"""
    shape = [1] * a.ndim
    shape[axis + 1] = -1
    idx = (yk - 1).reshape(shape)
    return np.take(np.take_along_axis(a, idx, axis=axis), 0, axis=axis)


def simlpart(S, H):
    """港: hihokensha/simlpart.py:simlpart。仕様: §2.4"""
    hy = S.hy
    ny = hy.n
    P = S.pol.get("hihokensha.part")
    A = S.pol.get("hihokensha.ages")
    lo, hi = A["kounen"]
    X = slice(lo, hi + 1)
    KB = P["kubun"]
    nk, step, off = int(KB["n"]), int(KB["step"]), int(KB["offset"])
    a1 = 1 * step + off - 2                              # kubun 1 の最初の年齢（15）
    partnin, nyk = H.partnin, H.partnin.shape[2]
    YK = slice(1, nyk)
    kbk, kjm = H.kbetu_partkiso, H.koyou_j_m
    ichigou, sangou, xend = H.ichigou, H.sangou, H.xend
    kp, ip = hy.i(S.partkyr), hy.i(S.part_start)
    n = ny - ip
    Y = slice(ip, ny)
    ktj = np.zeros((4, ny, 5, nk + 2))
    ntj = np.zeros((4, ny, 5, NAGE))
    kpg = np.zeros((8, ny, 5, nk + 2))
    kbn = np.zeros((8, 4, nyk, ny, 5, nk + 2))
    pw = np.zeros((3, 4, nyk, n, 5, NAGE))               # p_wari（pkubun 1〜2 だけ要る。年度は part_start〜）
    a2 = a1 + nk * step                                  # 90（区分の外）
    x20, x60, x70 = 20, 60, 70
    k20, k59 = (x20 - a1) // step + 1, (59 - a1) // step + 1                        # kubun 2〜9
    k60, k69 = (x60 - a1) // step + 1, (69 - a1) // step + 1                        # kubun 10〜11

    # 1. 年齢区分別の短時間雇用者数
    Yk = slice(kp, ny)
    K = kjm[:, Yk, 1:3, a1:a2].reshape(11, ny - kp, 2, nk, step).sum(-1)     # (11, n, 2, nk)
    ktj[1, Yk, 1:3, 1:nk + 1] = K[4] + K[5]
    ktj[2, Yk, 1:3, 1:nk + 1] = K[1] + K[2] + K[6]
    ktj[3, Yk, 1:3, 1:nk + 1] = K[3]
    # 2. 基礎数値を延ばす
    Y2 = slice(kp + 1, ny)
    base = ktj[1:4, kp, 1:3, 1:nk + 1]                                           # (3, 2, nk)
    if (base <= 0.).any():
        H.notes.append("パートの基礎年度の短時間雇用者が 0 以下: %d 区分" % int((base <= 0.).sum()))
    with np.errstate(**_ERR):
        ratio = np.where(base[:, None] > 0., ktj[1:4, Y2, 1:3, 1:nk + 1] / base[:, None], 0.)   # (3, n2, 2, nk)
    for p in (1, 2, 7):
        kbn[p, 1:4, YK, Y2, 1:3, 1:nk + 1] = kbk[p, 1:4, YK, 1:3, 1:nk + 1][:, :, None] * ratio[:, None]
    kbn[1, 1:4, YK, Y2, 1:3, k20:k59 + 1] += kbn[7, 1:4, YK, Y2, 1:3, k20:k59 + 1]
    kbn[7, 1:4, YK, Y2, 1:3, k20:k59 + 1] = 0.
    kbn[1, 2, YK, Y2, 1:3, 1:nk + 1] += kbn[2, 2, YK, Y2, 1:3, 1:nk + 1]
    kbn[2, 2, YK, Y2, 1:3, 1:nk + 1] = 0.
    kbn[0, 1:4, YK, Y2] = kbn[1, 1:4, YK, Y2] + kbn[2, 1:4, YK, Y2] + kbn[7, 1:4, YK, Y2]
    # 3. 元制度の人数で頭を打ち、割合を作る（part_start 年度以降）
    kpg[1, Y, 1:3, k20:k59 + 1] = ichigou[1, Y, 1:3, x20:x60].reshape(n, 2, -1, step).sum(-1)
    kpg[2, Y, 1:3, k20:k59 + 1] = sangou[0, Y, 1:3, x20:x60].reshape(n, 2, -1, step).sum(-1)
    kpg[1, Y, 1:3, k60:k69 + 1] = ichigou[2, Y, 1:3, x60:x70].reshape(n, 2, -1, step).sum(-1)
    _wari(kbn, kpg, pw, Y, slice(k20, k59 + 1), slice(1, 3), slice(x20, x60), step, YK, H)
    _wari(kbn, kpg, pw, Y, slice(k60, k69 + 1), slice(1, 2), slice(x60, x70), step, YK, H)
    pw[1:3, 1:4, YK, :, 3:5, x20:x70] = pw[1:3, 1:4, YK, :, 2, x20:x70][:, :, :, :, None]
    # 4. 年齢別の短時間雇用者数と、年齢別のパート
    ntj[1, Yk, 1:5, X] = kjm[4, Yk, 1:5, X] + kjm[5, Yk, 1:5, X]
    ntj[2, Yk, 1:5, X] = kjm[1, Yk, 1:5, X] + kjm[2, Yk, 1:5, X] + kjm[6, Yk, 1:5, X]
    ntj[3, Yk, 1:5, X] = kjm[3, Yk, 1:5, X]
    yk = ykubun(hy.labels()[Y], S)
    # 4a. 15〜19 歳: 元その他（区分 1 の値を年齢別の短時間雇用者数で割る）
    _sonota(partnin, kbn, ntj, ktj, Y, slice(a1, a1 + step), slice(1, 2), step, YK)
    # 4b. 20〜59 歳: 元1号（一般）・元3号
    X8 = slice(x20, x60)
    w1 = pw[1, 1:4, YK, :, 1:5, X8]
    w2 = pw[2, 1:4, YK, :, 1:5, X8]
    partnin[1, 1:4, YK, Y, 1:5, X8] = ichigou[1, Y, 1:5, X8][None, None] * w1
    for p, src in ((2, sangou[0]), (3, sangou[1]), (4, sangou[4]), (5, sangou[5]), (6, sangou[6])):
        partnin[p, 1:4, YK, Y, 1:5, X8] = src[Y, 1:5, X8][None, None] * w2
    partnin[1:7, 1:4, YK, Y, 0, X8] = partnin[1:7, 1:4, YK, Y, 1, X8] + partnin[1:7, 1:4, YK, Y, 2, X8]
    d = lambda p, Xs: _pick(partnin[p, 1:4, YK, Y, 1:5, Xs], yk, 1).sum(0)   # noqa: E731  当年度の段階ぶん（時間区分の和）
    ichigou[1, Y, 1:5, X8] -= d(1, X8)
    for seido, p in ((1, 3), (4, 4), (5, 5), (6, 6)):
        sangou[seido, Y, 1:5, X8] -= d(p, X8)
    ichigou[1, Y, 0, X8] = ichigou[1, Y, 1, X8] + ichigou[1, Y, 2, X8]
    for seido in (1, 4, 5, 6):
        sangou[seido, Y, 0, X8] = sangou[seido, Y, 1, X8] + sangou[seido, Y, 2, X8]
    # 4c. 60〜69 歳: 元1号（任意）と元その他
    X9 = slice(x60, x70)
    partnin[1, 1:4, YK, Y, 1:5, X9] = ichigou[2, Y, 1:5, X9][None, None] * pw[1, 1:4, YK, :, 1:5, X9]
    partnin[1, 1:4, YK, Y, 0, X9] = partnin[1, 1:4, YK, Y, 1, X9] + partnin[1, 1:4, YK, Y, 2, X9]
    ichigou[2, Y, 1:5, X9] -= d(1, X9)
    ichigou[2, Y, 0, X9] = ichigou[2, Y, 1, X9] + ichigou[2, Y, 2, X9]
    _sonota(partnin, kbn, ntj, ktj, Y, X9, slice(k60, k69 + 1), step, YK)
    # 4d. 45年化: 60 歳〜上限年齢の手前は元その他を元1号・元3号に配り直す（年度・年齢ごと。港 simlpart.c:383-541）
    if S.mode45 == 1:
        x60d = int(A["xend_default"])
        for y in range(ip, ny):
            for x in range(x60d, int(xend[y])):
                _mode45_part(S, H, y, x)
    # 5. 合計と累積
    Xo = slice(a1, 80)
    partnin[0, 1:4, YK, Y, :, Xo] = (partnin[1, 1:4, YK, Y, :, Xo] + partnin[2, 1:4, YK, Y, :, Xo]
                                     + partnin[7, 1:4, YK, Y, :, Xo])
    partnin[:, 0, YK, Y, :, Xo] = partnin[:, 1:4, YK, Y, :, Xo].sum(1)
    partnin[0, 0, 0, Y, :, Xo] += _pick(partnin[0, 0, YK, Y, :, Xo], yk)
    # 6. 足し込み（年度ごと。前年度の段階のぶんも要る）
    yk_prev = ykubun(hy.labels()[Y] - 1, S)
    for k, y in enumerate(range(ip, ny)):
        tashikomi(S, H, y, int(yk_prev[k]), int(yk[k]), just=(y == ip))
    # 7. 平均労働時間と計
    X7 = slice(lo, x70)
    kjc, sdm, sdc, hm, hc = H.koyou_j_c, H.soroudh_m, H.soroudh_c, H.heikinh_m, H.heikinh_c
    with np.errstate(**_ERR):
        hm[10, Y] = sdm[9, Y, 0, X7].sum(-1) / kjm[7, Y, 0, X7].sum(-1)
        hc[10, Y] = sdc[9, Y, 0, X7].sum(-1) / kjc[7, Y, 0, X7].sum(-1)
    ichigou[0, Y, :, X] = ichigou[1, Y, :, X] + ichigou[2, Y, :, X]
    inx = (np.arange(NAGE)[None, :] >= x20) & (np.arange(NAGE)[None, :] < xend[Y, None])
    sangou[0, Y] = np.where(inx[:, None, :], sangou[1, Y] + sangou[4, Y] + sangou[5, Y] + sangou[6, Y], sangou[0, Y])


def _mode45_part(S, H, y, x):
    """45年化のときの 60 歳以上のパート（1 年度・1 年齢）。元その他（pkubun 7）を 1号（一般）＋3号計 で頭を打ち、
    その割合で元1号（＋元3号）に配り、元1号が 1号一般を超えたぶんは元3号へ（逆も）、元3号を制度別に按分してから
    1号・3号から差し引く。港: hihokensha/simlpart.py:simlpart（`_mode45_part`。港も未検証の枝）"""
    P, ig, sg = H.partnin, H.ichigou, H.sangou
    yks = range(1, P.shape[2])
    yk_now = int(ykubun(S.hy.label(y), S))
    with np.errstate(**_ERR):
        for sei in range(1, 5):
            for t in (1, 2, 3):
                for yk in yks:
                    P[7, 0, yk, y, sei, x] += P[7, t, yk, y, sei, x]
            i1 = ig[1, y, sei, x]
            s0 = sg[0, y, sei, x]
            if i1 < 0. or s0 < 0.:
                raise ValueError("パート(45年化) %d年度の性%d、年齢%dの１号または３号がマイナス" % (S.hy.label(y), sei, x))
            for t in (1, 2, 3):
                for yk in yks:
                    if P[7, 0, yk, y, sei, x] > i1 + s0:
                        P[7, t, yk, y, sei, x] *= (i1 + s0) / P[7, 0, yk, y, sei, x]
                    w7 = P[7, t, yk, y, sei, x] / ((i1 + s0) if t != 2 else i1)
                    P[1, t, yk, y, sei, x] += i1 * w7
                    if t != 2:
                        P[2, t, yk, y, sei, x] = s0 * w7
                        for p, seido in ((3, 1), (4, 4), (5, 5), (6, 6)):
                            P[p, t, yk, y, sei, x] = sg[seido, y, sei, x] * w7
                    P[7, t, yk, y, sei, x] = 0.
            for p in (1, 2):
                for t in (1, 2, 3):
                    for yk in yks:
                        P[p, 0, yk, y, sei, x] += P[p, t, yk, y, sei, x]
            for t in (1, 2, 3):
                for yk in yks:
                    if t != 2:
                        i1b = ig[1, y, sei, x]
                        s0b = sg[0, y, sei, x]
                        if P[1, 0, yk, y, sei, x] > i1b:
                            tmp = P[1, 0, yk, y, sei, x] - i1b
                            tmq = P[1, t, yk, y, sei, x]
                            tmr = P[1, 1, yk, y, sei, x] + P[1, 3, yk, y, sei, x]
                            if tmr > 0.:
                                tms = tmp * (tmq / tmr)
                            else:
                                H.notes.append("パート %d年度の性%d、年齢%dの元１号の時間計がマイナス" % (S.hy.label(y), sei, x))
                                tms = 0.
                            P[1, t, yk, y, sei, x] -= tms
                            P[2, t, yk, y, sei, x] += tms
                        elif P[2, 0, yk, y, sei, x] > s0b:
                            tmp = P[2, 0, yk, y, sei, x] - s0b
                            tmq = P[2, t, yk, y, sei, x]
                            tmr = P[2, 1, yk, y, sei, x] + P[2, 3, yk, y, sei, x]
                            if tmr > 0.:
                                tms = tmp * (tmq / tmr)
                            else:
                                if sei != 4:
                                    H.notes.append("パート %d年度の性%d、年齢%dの元３号の時間計がマイナス" % (S.hy.label(y), sei, x))
                                tms = 0.
                            P[1, t, yk, y, sei, x] += tms
                            P[2, t, yk, y, sei, x] -= tms
                    if sei != 4:
                        s0c = sg[0, y, sei, x]
                        p2 = P[2, t, yk, y, sei, x]
                        for p, seido in ((3, 1), (4, 4), (5, 5), (6, 6)):
                            P[p, t, yk, y, sei, x] = p2 * sg[seido, y, sei, x] / s0c
            for t in (1, 2, 3):
                ig[1, y, sei, x] -= P[1, t, yk_now, y, sei, x]
                for p, seido in ((3, 1), (4, 4), (5, 5), (6, 6)):
                    sg[seido, y, sei, x] -= P[p, t, yk_now, y, sei, x]
    ig[1, y, 2, x] = ig[1, y, 3, x] + ig[1, y, 4, x]
    ig[1, y, 0, x] = ig[1, y, 1, x] + ig[1, y, 2, x]
    sg[:, y, 2, x] = sg[:, y, 3, x]
    sg[:, y, 0, x] = sg[:, y, 1, x] + sg[:, y, 2, x]
    P[1:8, 1:4, 1:, y, 2, x] = P[1:8, 1:4, 1:, y, 3, x] + P[1:8, 1:4, 1:, y, 4, x]
    P[1:8, 1:4, 1:, y, 0, x] = P[1:8, 1:4, 1:, y, 1, x] + P[1:8, 1:4, 1:, y, 2, x]


def _wari(kbn, kpg, pw, Y, Kb, Pb, Xb, step, YK, H):
    """年齢区分 `Kb`・元制度 `Pb` について、元制度の人数 `kpg` で頭を打ち、年齢別の割合 `pw` を作る。"""
    kbn[Pb, 0, YK, Y, 1:3, Kb] = kbn[Pb, 1:4, YK, Y, 1:3, Kb].sum(1)
    gen = kpg[Pb, Y, 1:3, Kb][:, None]                                  # (np, 1, n, 2, nk)
    tot = kbn[Pb, 0, YK, Y, 1:3, Kb]                                    # (np, nyk−1, n, 2, nk)
    with np.errstate(**_ERR):
        fac = np.where(gen < 0., 0., np.where(tot > gen, gen / tot, 1.))
    if (gen < 0.).any():
        H.notes.append("パートの元制度がマイナス: %d 箇所" % int((gen < 0.).sum()))
    if ((tot > gen) & (gen >= 0.)).any():
        H.notes.append("パートが元制度から減算しきれない（頭を打った）: %d 箇所" % int(((tot > gen) & (gen >= 0.)).sum()))
    kbn[Pb, 1:4, YK, Y, 1:3, Kb] *= fac[:, None]
    with np.errstate(**_ERR):
        v = kbn[Pb, 1:4, YK, Y, 1:3, Kb] / gen[:, None]                  # (np, 3, nyk−1, n, 2, nk)
    pw[Pb, 1:4, YK, :, 1:3, Xb] = np.repeat(v, step, axis=-1)


def _sonota(partnin, kbn, ntj, ktj, Y, Xb, Kb, step, YK):
    """元その他（pkubun 7）を年齢別に: 区分の値 × 年齢別の短時間雇用者 / 区分の短時間雇用者。女は有配偶・無配偶に割る。"""
    with np.errstate(**_ERR):
        q = kbn[7, 1:4, YK, Y, 1:3, Kb] / ktj[1:4, Y, 1:3, Kb][:, None]      # (3, nyk−1, n, 2, nk)
        q = np.repeat(q, step, axis=-1)
        partnin[7, 1:4, YK, Y, 1:3, Xb] = q * ntj[1:4, Y, 1:3, Xb][:, None]
        r = ntj[1:4, Y, 3:5, Xb] / ntj[1:4, Y, 2, Xb][:, :, None]             # (3, n, 2, nx)
        partnin[7, 1:4, YK, Y, 3:5, Xb] = partnin[7, 1:4, YK, Y, 2, Xb][:, :, :, None] * r[:, None]
    partnin[7, 1:4, YK, Y, 0, Xb] = partnin[7, 1:4, YK, Y, 1, Xb] + partnin[7, 1:4, YK, Y, 2, Xb]


def tashikomi(S, H, y, y1, y2, just):
    """パートを被用者数と総労働時間に足し込む（1 年度）。`y2` は当年度の段階、`y1` は前年度の段階。
    `just` なら年央は当年度の半分だけ。港: hihokensha/simlpart.py:tashikomi"""
    hrs = {int(k): float(v) for k, v in S.pol.get("hihokensha.part.hours").items()}
    h1, h2, h3 = hrs[1], hrs[2], hrs[3]
    Xo = slice(15, 80)
    partnin = H.partnin
    kjm, kjc, sdm, sdc = H.koyou_j_m, H.koyou_j_c, H.soroudh_m, H.soroudh_c
    p = partnin[0, :, y2, y, :, Xo]                       # (4, 5, 65): tkubun 0 計 / 1 / 2 / 3
    p0, p1, p2, p3 = p[0], p[1], p[2], p[3]
    kjm[7, y, :, Xo] += p0
    kjm[9, y, :, Xo] += p2
    kjm[10, y, :, Xo] += p1 + p3
    sdm[9, y, :, Xo] += p2 * h2 + p1 * h1 + p3 * h3
    sdm[7, y, :, Xo] += p2 * h2
    sdm[8, y, :, Xo] += p1 * h1 + p3 * h3
    if just:
        q0 = q1 = q2 = q3 = 0.
    else:
        q = partnin[0, :, y1, y - 1, :, Xo]
        q0, q1, q2, q3 = q[0], q[1], q[2], q[3]
    kjc[7, y, :, Xo] += (q0 + p0) / 2.
    kjc[9, y, :, Xo] += (q2 + p2) / 2.
    kjc[10, y, :, Xo] += (q1 + p1 + q3 + p3) / 2.
    sdc[9, y, :, Xo] += ((q2 + p2) * h2 + (q1 + p1) * h1 + (q3 + p3) * h3) / 2.
    sdc[7, y, :, Xo] += (q2 + p2) * h2 / 2.
    sdc[8, y, :, Xo] += ((q1 + p1) * h1 + (q3 + p3) * h3) / 2.
