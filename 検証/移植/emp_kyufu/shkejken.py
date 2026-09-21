# -*- coding: utf-8 -*-
"""
厚生年金/給付費推計/shkejken.cpp の忠実移植（受給権者の年金額を作る）
======================================================================
324 行。給付の種類 `i`（1〜13）・年齢 `x`・繰上げ繰下げの区分 `xx`
（0〜15）ごとに1回呼ばれ、

    t4k[x][xx][i]       受給権者数
    hn2k[x][xx][i][1,2] うち配偶者の区分別
    t6k[x][xx][i][j]    1人あたり年金額（j = 1〜23 の内訳）

を作る。`dtst()` が割り戻した「減額前・加算前」の額に、
繰上げ減額率・加給対象者割合・有子割合を**掛け直す**のが仕事。

`xrb` は 0 に落とすが `xxr` は落とさない
----------------------------------------
```c
xrb = 0;
if(i <= 4) {
  seps::sknr(k, x, xxr, xrb);
  xxr = max(60, xxr);
  xrb = max(60, xrb);
}
```

`xxr` `xrb` は**グローバル**。`i >= 5` のときは `sknr()` を呼ばないので

- `xrb` は 0（`xrb > 60` の枝に入らない）
- `xxr` は **前回の呼び出しが残した値のまま**

になる。`shke.cpp` の呼び出し順は

```c
FOR(i, 1, 13) FOR(xx, 0, 15) {
  if(i >= 5 && xx != 0) continue;
  FOR(x, 0, 114) seps::shkejken(i, x, xx);
}
```

なので、`i = 5` の最初の呼び出しが見る `xxr` は
**`i = 4, xx = 15, x = 114` のときの値**。`i = 5〜8` は

```c
if(x < xxr || (xx > 5 && x < 60+xx)) {
  t6k.AT(x, xx, i, 4)  = 0.0;   /* 加給年金 */
  ...
}
```

でその古い `xxr` を見る。`x = 114` の `xxr` は（男の場合）65 なので、
`i = 5〜8`（障害・通算）の加給年金が**64歳以下で全部 0 になる**。
`検証/原本の不具合.md` の E26。**そのまま写す**（移植版も
`G.xxr` を関数の外に持っているので自然にそうなる）。

`fhantei` `rhantei` `fpart` は `siml()` が入れる
------------------------------------------------
長い条件

    flg_hantei == 0 && k >= KIJUN + 1 && pseid == 0 && s <= 2 && xx == 0

の枝で `rhantei` `fhantei` を使う。この2つ（と最後に使う `fpart`）を
埋めるのは **`siml.cpp`**（`rhantei` は 336〜370行、`fpart` は
237〜306行）。

`sepsd.cpp` の並びは

    k = KIJUN   … dtst() → shke()              ← siml() の前
    k = KIJUN+1 … siml() → shke()
    k = KIJUN+2 … siml() → shke()
    …

なので、**`k == KIJUN` の shke では 0**（`zero_sepsd()` のまま）で、
条件の `k >= KIJUN + 1` がちょうどそれを避けている。
`k >= KIJUN + 1` では前の年度の `siml()` が入れた値が入っている。

段階ごとの突き合わせ（`test_kyufu_stage.py` の `shke` 段階）は
`k = KIJUN` の1年度だけなので、**この枝は通らない**。
`siml()` を移植したあと、`k` のループを回して初めて効く。
"""
from glva import G
from sepsstd import c_round, std_max
from setconst import KIJUN
from sknr import sknr

__all__ = ["shkejken"]


def shkejken(i, x, xx):
    """shkejken.cpp:4 の忠実移植。"""
    k = G.k
    s = G.s
    s2 = G.s2
    pseid = G.pseid

    t4k = G.t4k
    t6k = G.t6k
    f = G.f
    f_min = G.f_min
    f_hik = G.f_hik

    # `xrb` はグローバル。0 に落とす（`i >= 5` では sknr を呼ばない）
    G.xrb = 0
    if i <= 4:
        sknr(k, x)
        G.xxr = max(60, G.xxr)
        G.xrb = max(60, G.xrb)
    xxr = G.xxr                     # `i >= 5` では前回の値（E26）
    xrb = G.xrb

    hantei = (G.flg_hantei == 0 and k >= KIJUN + 1 and pseid == 0
              and s <= 2 and xx == 0 and 1 <= i <= 4)
    # 判定の対象になる生年（足元の65〜70歳と、その1〜2年あと）
    hantei_kx = ((KIJUN + 1 - 70 <= k - x <= KIJUN + 1 - 65)
                 or (s == 1 and k - x == KIJUN + 2 - 65)
                 or (s == 2 and (k - x == KIJUN + 2 - 65
                                 or k - x == KIJUN + 3 - 65)))

    skip_jken = ((xrb > 60 and x < 65 - xx and x < xrb and xx <= 5)
                 or (xx > 5 and x < 60 + xx))

    if not skip_jken:
        t4k[x, xx, i] = G.r[x, xx, i]

        if hantei:
            tmp1 = 0.0
            if hantei_kx:
                if i == 2:
                    t4k[x, xx, i] = G.r[x, xx, i] + G.rhantei[x, xx, i]
                if i == 4:
                    t4k[x, xx, i] = std_max(
                        G.r[x, xx, i] + G.rhantei[x, xx, i],
                        G.r[x, xx, i] * G.routsu[s, i, 1])
                    tmp1 += (-G.rhantei[x, xx, i]
                             - (G.r[x, xx, i] - t4k[x, xx, i]))
                    t4k[x, xx, 2] -= tmp1
            else:
                if i == 1:
                    t4k[x, xx, i] = G.r[x, xx, i] - (
                        G.rhantei[x, xx, 2] + G.rhantei[x, xx, 3]
                        + G.rhantei[x, xx, 4])
                if i == 2:
                    t4k[x, xx, i] = G.r[x, xx, i] + G.rhantei[x, xx, i]
                if i == 3:
                    t4k[x, xx, i] = std_max(
                        G.r[x, xx, i] + G.rhantei[x, xx, i],
                        G.r[x, xx, i] * G.routsu[s, i, 1])
                    tmp1 += (-G.rhantei[x, xx, i]
                             - (G.r[x, xx, i] - t4k[x, xx, i]))
                if i == 4:
                    t4k[x, xx, i] = std_max(
                        G.r[x, xx, i] + G.rhantei[x, xx, i],
                        G.r[x, xx, i] * G.routsu[s, i, 1])
                    tmp1 += (-G.rhantei[x, xx, i]
                             - (G.r[x, xx, i] - t4k[x, xx, i]))
                    t4k[x, xx, 1] -= tmp1

        G.hn2k[x, xx, i, 1] = G.hn[x, xx, i, 1]
        G.hn2k[x, xx, i, 2] = G.hn[x, xx, i, 2]

    # 特別支給の老齢厚生年金（60〜69歳の繰上げなし）を足す
    if i == 1 and xx == 0 and 60 <= x <= 69 and xxr > 60:
        t4k[x, 0, 1] += G.rsen[x]
        G.hn2k[x, 0, 1, 1] += G.hnsen[x, 1]
        G.hn2k[x, 0, 1, 2] += G.hnsen[x, 2]

    # ------------------------------------------------------------------
    # 本来水準・従前額保障・8割下限の高い方を取る
    # ------------------------------------------------------------------
    skip_j = ((i <= 8 and x >= 60 and xrb > 60 and x < 65 - xx
               and x < xrb and xx <= 5)
              or (xx > 5 and x < 60 + xx))

    if not skip_j:
        for j in range(1, 23 + 1):
            if j == 14 or j == 21:
                t6k[x, xx, i, j] = std_max(f[x, xx, i, j],
                                           f_min[x, xx, i, j])
            elif j == 1 or j == 10:
                t6k[x, xx, i, j] = std_max(
                    std_max(f[x, xx, i, j], f_hik[x, xx, i, j]),
                    f_min[x, xx, i, j])
            elif j != 13 and j != 22:
                t6k[x, xx, i, j] = std_max(f[x, xx, i, j],
                                           f_min[x, xx, i, j])

            if hantei and (j == 1 or 3 <= j <= 6 or j == 14 or j == 23):
                tmp2 = 0.0
                tmf = 0.0
                if (3 <= j <= 6) or j == 23:
                    n = 1
                if j == 1:
                    n = 2
                if j == 14:
                    n = 3

                if hantei_kx:
                    if i == 2:
                        t6k[x, xx, i, j] += G.fhantei[x, xx, i, j]
                    if i == 4:
                        tmf = t6k[x, xx, i, j]
                        t6k[x, xx, i, j] = std_max(
                            t6k[x, xx, i, j] + G.fhantei[x, xx, i, j],
                            t6k[x, xx, i, j] * G.routsu[s, i, n])
                        tmp2 += (-G.fhantei[x, xx, i, j]
                                 - (tmf - t6k[x, xx, i, j]))
                        t6k[x, xx, 2, j] -= tmp2
                else:
                    if i == 1:
                        t6k[x, xx, i, j] += -(
                            G.fhantei[x, xx, 2, j] + G.fhantei[x, xx, 3, j]
                            + G.fhantei[x, xx, 4, j])
                    if i == 2:
                        t6k[x, xx, i, j] += G.fhantei[x, xx, i, j]
                    if i == 3:
                        t6k[x, xx, i, j] = std_max(
                            t6k[x, xx, i, j] + G.fhantei[x, xx, i, j],
                            t6k[x, xx, i, j] * G.routsu[s, i, n])
                        # `i == 3` だけ `tmf` ではなく `f` を引く
                        tmp2 += (-G.fhantei[x, xx, i, j]
                                 - (f[x, xx, i, j] - t6k[x, xx, i, j]))
                    if i == 4:
                        tmf = t6k[x, xx, i, j]
                        t6k[x, xx, i, j] = std_max(
                            t6k[x, xx, i, j] + G.fhantei[x, xx, i, j],
                            t6k[x, xx, i, j] * G.routsu[s, i, n])
                        tmp2 += (-G.fhantei[x, xx, i, j]
                                 - (tmf - t6k[x, xx, i, j]))
                        t6k[x, xx, 1, j] -= tmp2

    # ------------------------------------------------------------------
    # 遺族（i = 11, 12）の有子・無子の振り分け
    # ------------------------------------------------------------------
    if i == 11 or i == 12:
        if x >= 19:
            rck = G.rc[s, k, x]
            if s2 != 2:
                t6k[x, xx, i, 14] *= rck
                t6k[x, xx, i, 17] *= rck
                t6k[x, xx, i, 7] *= 1.0 - rck
                t6k[x, xx, i, 8] *= 1.0 - rck
                t6k[x, xx, i, 18] *= 1.0 - rck
            else:
                t6k[x, xx, i, 14] *= rck
                t6k[x, xx, i, 17] = 0.0
                t6k[x, xx, i, 18] = 0.0
                t6k[x, xx, i, 20] = 0.0
    if i == 13 and x >= 19 and s2 == 2:
        t6k[x, xx, i, 17] = 0.0

    # ------------------------------------------------------------------
    # 繰上げ減額・繰下げ増額を掛ける
    # ------------------------------------------------------------------
    if i <= 4:
        if k >= 22 and k - 22 >= x - 60:
            jj = 1
        else:
            jj = 0

        if x >= 60 and xrb > 60 and xx <= 5 and 65 - xx < xrb:
            tmgbe = G.rigbe[s2, 65 - xx, xrb, jj]
            t6k[x, xx, i, 1] *= tmgbe

        if xx <= 5:
            tmgd = G.rigd[s2, 65 - xx, xxr, jj]
            tmgk = G.rigk[s2, 65 - xx, xxr, jj]

            if xrb > 60 and 65 - xx < xrb:
                if x < 65 - xx:
                    t6k[x, xx, i, 3] = 0.0
                else:
                    t6k[x, xx, i, 3] *= tmgk
            else:
                if x < 65:
                    t6k[x, xx, i, 3] = 0.0

            if x < 65 - xx:
                t6k[x, xx, i, 14] = 0.0
                if x < xxr and xxr > 60:
                    t6k[x, xx, i, 2] = 0.0
            elif x < 65:
                t6k[x, xx, i, 2] *= tmgd
                t6k[x, xx, i, 14] *= tmgk
            elif x >= 65:
                t6k[x, xx, i, 2] = 0.0
                t6k[x, xx, i, 14] *= tmgd + tmgk
        elif xx > 5:
            if x < 60 + xx:
                t6k[x, xx, i, 1] = 0.0
                t6k[x, xx, i, 2] = 0.0
                t6k[x, xx, i, 3] = 0.0
                t6k[x, xx, i, 14] = 0.0
            else:
                tmgbe = 1.0 + 0.007 * (xx - 5) * 12.0
                t6k[x, xx, i, 1] *= tmgbe
                t6k[x, xx, i, 2] = 0.0
                t6k[x, xx, i, 3] *= tmgbe
                t6k[x, xx, i, 14] *= tmgbe

    # ------------------------------------------------------------------
    # 加給年金・振替加算の対象者割合を掛ける
    # ------------------------------------------------------------------
    adt_3_2 = G.adt[3] / G.adt[2]
    ii = None
    if i <= 8:
        if i <= 2:
            ii = 1
        elif i <= 4:
            ii = 6
        else:
            ii = 2
        t6k[x, xx, i, 4] *= G.kd[k, ii, 1, x]
        t6k[x, xx, i, 5] *= (G.kd[k, ii, 2, x]
                             + G.kd[k, ii, 3, x] * adt_3_2)
        t6k[x, xx, i, 6] *= G.kd[k, ii, 4, x]
        t6k[x, xx, i, 19] *= G.kd[k, ii, 1, x]
        t6k[x, xx, i, 23] *= G.kd[k, ii, 1, x]
        if x < xxr or (xx > 5 and x < 60 + xx):
            t6k[x, xx, i, 4] = 0.0
            t6k[x, xx, i, 5] = 0.0
            t6k[x, xx, i, 6] = 0.0
            t6k[x, xx, i, 19] = 0.0
            t6k[x, xx, i, 23] = 0.0
    elif i <= 10:
        if i == 9:
            ii = 3
        else:
            ii = 4

        t6k[x, xx, i, 4] *= G.kd[k, ii, 1, x]
        t6k[x, xx, i, 5] *= (G.kd[k, ii, 2, x]
                             + G.kd[k, ii, 3, x] * adt_3_2)
        t6k[x, xx, i, 6] *= G.kd[k, ii, 4, x]
        t6k[x, xx, i, 19] *= G.kd[k, ii, 1, x]
        t6k[x, xx, i, 20] *= (G.kd[k, ii, 2, x]
                              + G.kd[k, ii, 3, x] * adt_3_2)
        t6k[x, xx, i, 21] *= (G.kd[k, ii, 2, x]
                              + G.kd[k, ii, 3, x] * adt_3_2)
    else:
        # `ii` はここでは代入されない（下の `i == 1` の枝では 1）
        t6k[x, xx, i, 5] *= (G.kd[k, 5, 2, x] + G.kd[k, 5, 3, x] * adt_3_2)
        t6k[x, xx, i, 20] *= (G.kd[k, 5, 2, x] + G.kd[k, 5, 3, x] * adt_3_2)
        t6k[x, xx, i, 21] *= (G.kd[k, 5, 2, x] + G.kd[k, 5, 3, x] * adt_3_2)

    # 特別支給の老齢厚生年金の年金額を足す
    if i == 1 and xx == 0 and 60 <= x <= 69 and xxr > 60:
        tmfsen = [0.0] * 24
        for j in range(1, 23 + 1):
            tmfsen[j] = G.fsen[x, j]
            if j == 1 or j == 10:
                tmfsen[j] = std_max(G.fsen[x, j], G.fsenhik[x, j])
            tmfsen[j] = std_max(tmfsen[j], G.fsenmin[x, j])
        t6k[x, 0, 1, 1] += tmfsen[1]
        t6k[x, 0, 1, 2] += tmfsen[2]
        t6k[x, 0, 1, 4] += tmfsen[4] * G.kd[k, ii, 1, x]
        t6k[x, 0, 1, 5] += tmfsen[5] * (G.kd[k, ii, 2, x]
                                        + G.kd[k, ii, 3, x] * adt_3_2)
        t6k[x, 0, 1, 23] += tmfsen[23] * G.kd[k, ii, 1, x]

    if x >= 65 or x < 40:
        t6k[x, xx, i, 7] = 0.0
    if x < 65:
        t6k[x, xx, i, 8] = 0.0
        t6k[x, xx, i, 15] = 0.0
        t6k[x, xx, i, 16] = 0.0

    # 経過的な差額（12番）から重なるぶんを引く
    if i == 12:
        t6k[x, xx, i, 12] = std_max(
            0.0,
            t6k[x, xx, i, 12] - t6k[x, xx, i, 10] - t6k[x, xx, i, 5]
            - t6k[x, xx, i, 9] - t6k[x, xx, i, 11])
    else:
        t6k[x, xx, i, 12] = std_max(
            0.0,
            t6k[x, xx, i, 12] - t6k[x, xx, i, 10] - t6k[x, xx, i, 11])

    # 配偶者の年齢（`ns` を四捨五入）で振替加算の有無を決める
    if x >= 15:
        nsx = int(c_round(G.ns[k, x]))
        if nsx < 65 or k - nsx < -74:
            t6k[x, xx, i, 6] = 0.0
        if k - nsx >= -74:
            t6k[x, xx, i, 18] = 0.0

    # 適用拡大で在職に移るぶんを老齢から付け替える
    if pseid == 0 and s <= 2 and k >= G.partyr3 and 60 <= x <= 70:
        if i == 1:
            t6k[x, xx, i, 1] -= G.fpart[x, xx, 1]
        elif i == 2:
            t6k[x, xx, i, 1] += G.fpart[x, xx, 1]
        elif i == 3:
            t6k[x, xx, i, 1] -= G.fpart[x, xx, 2]
        elif i == 4:
            t6k[x, xx, i, 1] += G.fpart[x, xx, 2]
