# -*- coding: utf-8 -*-
"""
厚生年金/給付費推計/dsitk.cpp の忠実移植（裁定時の期間・支給開始年齢・報酬比例額）
==================================================================================
399 行。裁定（年金を受け始めること）のときの

    it     加入期間による資格の種類（1 新法25年 / 2 旧法中高齢 / 3 20年 / 4 該当なし）
    xr     旧法の支給開始年齢（55〜60）
    xxr    定額部分の支給開始年齢
    xrb    報酬比例部分の支給開始年齢
    tn     加入年数（加入可能年数で切る）
    ta     ある区分の期間
    pro    報酬比例部分の乗率（本来水準）
    pros   同（従前額保障）
    tz[1〜4] 期間の内訳
    pslr   過去分試算の按分率
    bk / bk2 / bk3  報酬比例部分の年金額（本来・パート・8割下限）

を作る。呼ぶのは `simlsaite1.cpp`（`ii` = 9, 15, 16, 17）と
`simlsaite2.cpp`（`ii` = 1, 2）。`bk` `bk2` `bk3` は参照引数で返し、
残りは**グローバルに書く**。移植版は `(bk, bk2, bk3)` をタプルで返す。

`ii` の意味
-----------
| `ii` | 誰の裁定か | 読む配列 |
|---|---|---|
| 1 | 在職の被保険者（`ze`） | `ze` `we` |
| 2 | 退職した被保険者（`z`） | `z` `w` |
| 9 | 障害（新法） | `z` の年齢を1つ戻したもの ＋ `w` |
| 15 | 障害（本来水準） | 同上 |
| 16 | 障害（従前額保障） | 同上 |
| 17 | 在職の障害（`ze`） | `ze` `we` |

`tz = VEC(double, 4)` はグローバルの作り直し
--------------------------------------------
```c
tz = VEC(double, 4);
```

`tz` は**グローバル**（`zero.cpp:22` で同じ寸法で作る）。
これは「5要素の 0 で埋めたベクトルを作って代入する」ので、
実質**ゼロクリア**。移植版は `G.tz[:] = 0.0`。

`it` の判定は生年で刻みが違う
-----------------------------
```c
if( kx >= -48 && tmp.AT(1) >= 20.0 - 1.0e-6) it = 3;

if((kx <= -54 && tmp.AT(2) >= 15.0 - 1.0e-6)  ||
   (kx == -53 && tmp.AT(2) >= 16.0 - 1.0e-6)  || … ) it = 1;
```

`kx = k - x` は生年度 − 2000。旧法の中高齢の特例（生年で
15年→24年に刻む）と、新法の 25年（`kx >= -44`）を書いている。
`it` は 3 → 1 → 2 の順に上書きするので、**最後に当たったものが残る**。

`ii == 9` の枝で `if(ii == 9)` と `else` の中身が同じ
-----------------------------------------------------
```c
if(ii == 9) {
  bk = (wd.AT(0) * prb + wd2.AT(0) * prbs) * 25.0 / min(zd.AT(0, 0), 25.0);
  …
} else {
  bk = (wd.AT(0) * prb + wd2.AT(0) * prbs) * 25.0 / min(zd.AT(0, 0), 25.0);
  …
}
```

**1文字違わず同じ**（`key == 12` の枝と通常の枝、合わせて4か所）。
`ii == 15` のときに `pro` `pros` を使い分けるつもりだったと読める
（すぐ上の `ii == 15 && zd >= 25.0` の枝はそうしている）。
`検証/原本の不具合.md` の E18 の仲間。

`xr` は `konen == 1 && it == 2` のときだけ 60 未満になる
-------------------------------------------------------
旧法の中高齢（`it == 2`）は生年によって 55〜59 歳から出る。
`assert(xr <= 65)` は `xr` が 55〜60 なので必ず通る。
"""
from glva import G
from sepsstd import std_max, std_min
from setconst import C19

__all__ = ["dsitk"]


def dsitk(x, t, ii):
    """dsitk.cpp:6 の忠実移植。`(bk, bk2, bk3)` を返す。"""
    k = G.k
    s2 = G.s2
    key = G.key
    psly = G.psly
    konen = G.konen
    xend = G.xend

    tmp = [0.0] * 5
    zd = None
    pszd = None
    wd = [0.0] * 4
    wd2 = [0.0] * 4
    zem = None
    pszem = None
    wem = [0.0] * 4
    wem2 = [0.0] * 4

    G.it = 4
    G.xr = 0
    bk = 0.0
    bk2 = 0.0
    bk3 = 0.0
    G.tn = 0.0
    G.ta = 0.0
    G.tz[:] = 0.0                   # 原本は `tz = VEC(double, 4)`

    kx = k - x
    kx_74 = max(kx, -74)

    kako = (key == 12 and k >= psly)

    if ii == 1:
        tmp[1] = G.ze[x, t, 0, 0]
        tmp[2] = G.ze[x, t, 0, 5]
        tmp[3] = G.ze[x, t, 1, 0]
        tmp[4] = G.ze[x, t, 1, 5]
        if kako:
            tmp[1] = G.psze[x, t, 0, 0]
            tmp[2] = G.psze[x, t, 0, 5]
            tmp[3] = G.psze[x, t, 1, 0]
            tmp[4] = G.psze[x, t, 1, 5]
    elif ii == 2:
        tmp[1] = G.z[x, t, 0, 0]
        tmp[2] = G.z[x, t, 0, 5]
        tmp[3] = G.z[x, t, 1, 0]
        tmp[4] = G.z[x, t, 1, 5]
        if kako:
            tmp[1] = G.psz[x, t, 0, 0]
            tmp[2] = G.psz[x, t, 0, 5]
            tmp[3] = G.psz[x, t, 1, 0]
            tmp[4] = G.psz[x, t, 1, 5]
    elif ii == 9 or ii == 15 or ii == 16:
        zd = [[0.0] * 7 for _ in range(2)]
        pszd = [[0.0] * 7 for _ in range(2)]
        for j in range(0, 6 + 1):
            for i in range(0, 1 + 1):
                if (j == 0 or j == 4
                        or (s2 == 1 and x >= 40 and j == 5)
                        or (s2 >= 2 and x >= 35 and j == 5)
                        or (20 <= x <= 60 and j == 6)):
                    if ((s2 != 3 and i == 0)
                            or (s2 == 3 and (i == 0 or i == 1))):
                        ch = 0.5
                    else:
                        ch = 0.0
                else:
                    ch = 0.0
                if kako:
                    if x < xend:
                        pszd[i][j] = std_max(0.0, G.psz[x, t, i, j] - ch)
                    else:
                        pszd[i][j] = std_max(0.0, G.psz[x - 1, t, i, j] - ch)
                    ch = 0.0
                if not kako:
                    if x < xend:
                        zd[i][j] = std_max(0.0, G.z[x, t, i, j] - ch)
                    else:
                        zd[i][j] = std_max(0.0, G.z[x - 1, t, i, j] - ch)
                else:
                    if x < xend:
                        zd[i][j] = G.z[x, t, i, j]
                    else:
                        zd[i][j] = G.z[x - 1, t, i, j]
        for i2 in range(0, 3 + 1):
            if not kako:
                if x < xend:
                    wd[i2] = G.w[x, t, 0, 0, i2]
                    wd2[i2] = std_max(0.0, G.w[x, t, 0, 4, i2]
                                      - G.chwd[x, t, i2])
                else:
                    wd[i2] = G.w[x - 1, t, 0, 0, i2]
                    wd2[i2] = std_max(0.0, G.w[x - 1, t, 0, 4, i2]
                                      - G.chwd[x - 1, t, i2])
            else:
                if x < xend:
                    wd[i2] = G.w[x, t, 0, 0, i2]
                    wd2[i2] = G.w[x, t, 0, 4, i2]
                else:
                    wd[i2] = G.w[x - 1, t, 0, 0, i2]
                    wd2[i2] = G.w[x - 1, t, 0, 4, i2]
    elif ii == 17:
        zem = [[0.0] * 7 for _ in range(2)]
        pszem = [[0.0] * 7 for _ in range(2)]
        for j in range(0, 6 + 1):
            for i in range(0, 1 + 1):
                zem[i][j] = G.ze[x, t, i, j]
                if kako:
                    pszem[i][j] = G.psze[x, t, i, j]
        tmp[1] = zem[0][0]
        tmp[2] = zem[0][5]
        tmp[3] = zem[1][0]
        tmp[4] = zem[1][5]
        if kako:
            tmp[1] = pszem[0][0]
            tmp[2] = pszem[0][5]
            tmp[3] = pszem[1][0]
            tmp[4] = pszem[1][5]
        for i2 in range(0, 3 + 1):
            wem[i2] = G.we[x, t, 0, 0, i2]
            wem2[i2] = G.we[x, t, 0, 4, i2]

    # ------------------------------------------------------------------
    # it — 加入期間による資格の種類。3 → 1 → 2 の順に上書きする
    # ------------------------------------------------------------------
    if kx >= -48 and tmp[1] >= 20.0 - 1.0e-6:
        G.it = 3

    if ((kx <= -54 and tmp[2] >= 15.0 - 1.0e-6)
            or (kx == -53 and tmp[2] >= 16.0 - 1.0e-6)
            or (kx == -52 and tmp[2] >= 17.0 - 1.0e-6)
            or (kx == -51 and tmp[2] >= 18.0 - 1.0e-6)
            or (kx == -50 and tmp[2] >= 19.0 - 1.0e-6)
            or (kx <= -49 and tmp[1] >= 20.0 - 1.0e-6)
            or (kx == -48 and tmp[1] >= 21.0 - 1.0e-6)
            or (kx == -47 and tmp[1] >= 22.0 - 1.0e-6)
            or (kx == -46 and tmp[1] >= 23.0 - 1.0e-6)
            or (kx == -45 and tmp[1] >= 24.0 - 1.0e-6)
            or (kx >= -44 and tmp[1] >= 25.0 - 1.0e-6)):
        G.it = 1

    if ((kx <= -54 and tmp[4] >= 15.0 - 1.0e-6)
            or (kx == -53 and tmp[4] >= 16.0 - 1.0e-6)
            or (kx == -52 and tmp[4] >= 17.0 - 1.0e-6)
            or (kx == -51 and tmp[4] >= 18.0 - 1.0e-6)
            or (kx == -50 and tmp[4] >= 19.0 - 1.0e-6)
            or (kx <= -49 and tmp[3] >= 20.0 - 1.0e-6)
            or (kx == -48 and tmp[3] >= 21.0 - 1.0e-6)
            or (kx == -47 and tmp[3] >= 22.0 - 1.0e-6)
            or (kx == -46 and tmp[3] >= 23.0 - 1.0e-6)
            or (kx == -45 and tmp[3] >= 24.0 - 1.0e-6)
            or (kx >= -44 and tmp[3] >= 25.0 - 1.0e-6)):
        G.it = 2

    # ------------------------------------------------------------------
    # 支給開始年齢
    # ------------------------------------------------------------------
    if ii <= 8 or ii == 17:
        G.xr = 60

        if konen == 1 and G.it == 2:
            if kx <= -55:
                G.xr = 55
            if -54 <= kx <= -53:
                G.xr = 56
            if -52 <= kx <= -51:
                G.xr = 57
            if -50 <= kx <= -49:
                G.xr = 58
            if -48 <= kx <= -47:
                G.xr = 59

        G.xxr = G.xr

        if (s2 == 1 and G.it != 2) or konen != 1:
            if -59 <= kx <= -58:
                G.xxr = 61
            if -57 <= kx <= -56:
                G.xxr = 62
            if -55 <= kx <= -54:
                G.xxr = 63
            if -53 <= kx <= -52:
                G.xxr = 64
            if kx >= -51:
                G.xxr = 65
        elif s2 == 2 and G.it != 2:
            if -54 <= kx <= -53:
                G.xxr = 61
            if -52 <= kx <= -51:
                G.xxr = 62
            if -50 <= kx <= -49:
                G.xxr = 63
            if -48 <= kx <= -47:
                G.xxr = 64
            if kx >= -46:
                G.xxr = 65
        else:
            if -42 <= kx <= -41:
                G.xxr = 61
            if -40 <= kx <= -39:
                G.xxr = 62
            if -38 <= kx <= -37:
                G.xxr = 63
            if -36 <= kx <= -35:
                G.xxr = 64
            if kx >= -34:
                G.xxr = 65

        G.xrb = G.xr

        if (s2 == 1 and G.it != 2) or konen != 1:
            if -47 <= kx <= -46:
                G.xrb = 61
            if -45 <= kx <= -44:
                G.xrb = 62
            if -43 <= kx <= -42:
                G.xrb = 63
            if -41 <= kx <= -40:
                G.xrb = 64
            if kx >= -39:
                G.xrb = 65
        elif s2 == 2 and G.it != 2:
            if -42 <= kx <= -41:
                G.xrb = 61
            if -40 <= kx <= -39:
                G.xrb = 62
            if -38 <= kx <= -37:
                G.xrb = 63
            if -36 <= kx <= -35:
                G.xrb = 64
            if kx >= -34:
                G.xrb = 65
        else:
            G.xrb = G.xxr

        assert G.xr <= 65

    # ------------------------------------------------------------------
    # 報酬比例部分の乗率
    # ------------------------------------------------------------------
    G.pro = 0.0
    G.pros = 0.0
    if -74 <= kx <= -54:
        G.pro = G.pre[C19(kx)]
        G.pros = G.pres[C19(kx)]
    elif kx > -54:
        G.pro = G.prb
        G.pros = G.prbs
    else:
        G.pro = G.pra
        G.pros = G.pras

    # ------------------------------------------------------------------
    # 期間の内訳と報酬比例額
    # ------------------------------------------------------------------
    if ii == 1:
        ze = G.ze
        G.tz[1] = (ze[x, t, 0, 0] - ze[x, t, 0, 2] - ze[x, t, 0, 3]
                   - ze[x, t, 0, 4])
        G.tz[2] = ze[x, t, 0, 2] + ze[x, t, 0, 3] + ze[x, t, 0, 4]
        G.tz[3] = ze[x, t, 0, 1] + ze[x, t, 0, 2] + ze[x, t, 0, 3]
        G.tz[4] = ze[x, t, 0, 0] - ze[x, t, 0, 4]

        if kako:
            G.tn = G.psze[x, t, 0, 0]
        else:
            G.tn = ze[x, t, 0, 0]

        G.tn = std_min(G.tn, G.can2[C19(kx_74)])

        G.ta = ze[x, t, 0, 6]
        if G.tz[3] > 1.0e-6:
            tmq = G.tz[4] / G.tz[3]
        else:
            tmq = 0.0
        bk = ((G.we[x, t, 0, 0, 0] * tmq * G.pro
               + G.we[x, t, 0, 4, 0] * G.pros) * G.hikrate)
        bk2 = (G.we[x, t, 0, 0, 2] * tmq * G.pro
               + G.we[x, t, 0, 4, 2] * G.pros)
        bk3 = ((G.we[x, t, 0, 0, 3] * tmq * G.pro
                + G.we[x, t, 0, 4, 3] * G.pros) * G.hikrate * 0.8)
        G.pslr = 1.0
        if kako:
            if G.psze[x, t, 0, 0] > 1.0e-6:
                G.pslr = std_min(1.0, ze[x, t, 0, 0] / G.psze[x, t, 0, 0])
            else:
                G.pslr = 0.0
            G.tn *= G.pslr

    elif ii == 2:
        z = G.z
        G.tz[1] = (z[x, t, 0, 0] - z[x, t, 0, 2] - z[x, t, 0, 3]
                   - z[x, t, 0, 4])
        G.tz[2] = z[x, t, 0, 2] + z[x, t, 0, 3] + z[x, t, 0, 4]
        G.tz[3] = z[x, t, 0, 1] + z[x, t, 0, 2] + z[x, t, 0, 3]
        G.tz[4] = z[x, t, 0, 0] - z[x, t, 0, 4]

        if kako:
            G.tn = G.psz[x, t, 0, 0]
        else:
            G.tn = z[x, t, 0, 0]

        G.tn = std_min(G.tn, G.can2[C19(kx_74)])

        G.ta = z[x, t, 0, 6]
        if G.tz[3] > 1.0e-6:
            tmq = G.tz[4] / G.tz[3]
        else:
            tmq = 0.0
        bk = ((G.w[x, t, 0, 0, 0] * tmq * G.pro
               + G.w[x, t, 0, 4, 0] * G.pros) * G.hikrate)
        bk2 = (G.w[x, t, 0, 0, 2] * tmq * G.pro
               + G.w[x, t, 0, 4, 2] * G.pros)
        bk3 = ((G.w[x, t, 0, 0, 3] * tmq * G.pro
                + G.w[x, t, 0, 4, 3] * G.pros) * G.hikrate * 0.8)
        G.pslr = 1.0
        if kako:
            if G.psz[x, t, 0, 0] > 1.0e-6:
                G.pslr = std_min(1.0, z[x, t, 0, 0] / G.psz[x, t, 0, 0])
            else:
                G.pslr = 0.0
            G.tn = G.tn * G.pslr

    elif ii == 9 or ii == 15 or ii == 16:
        G.tz[1] = zd[0][0] - zd[0][2] - zd[0][3] - zd[0][4]
        G.tz[2] = zd[0][2] + zd[0][3] + zd[0][4]
        if kako:
            if ii == 9 and pszd[0][0] >= 25.0:
                bk = wd[0] * G.prb + wd2[0] * G.prbs
                bk2 = wd[2] * G.prb + wd2[2] * G.prbs
                bk3 = wd[3] * G.prb + wd2[3] * G.prbs
            elif ii == 15 and pszd[0][0] >= 25.0:
                bk = wd[0] * G.pro + wd2[0] * G.pros
                bk2 = wd[2] * G.pro + wd2[2] * G.pros
                bk3 = wd[3] * G.pro + wd2[3] * G.pros
            elif ii == 16:
                bk = wd[0] * G.prb + wd2[0] * G.prbs
                bk2 = wd[2] * G.prb + wd2[2] * G.prbs
                bk3 = wd[3] * G.prb + wd2[3] * G.prbs
            else:
                if pszd[0][0] > 1.0e-6:
                    # 原本は `if(ii == 9)` と `else` の中身が同じ
                    d = std_min(pszd[0][0], 25.0)
                    bk = (wd[0] * G.prb + wd2[0] * G.prbs) * 25.0 / d
                    bk2 = (wd[2] * G.prb + wd2[2] * G.prbs) * 25.0 / d
                    bk3 = (wd[3] * G.prb + wd2[3] * G.prbs) * 25.0 / d
                else:
                    bk = 0.0
                    bk2 = 0.0
                    bk3 = 0.0
        else:
            if ii == 9 and zd[0][0] >= 25.0:
                bk = wd[0] * G.prb + wd2[0] * G.prbs
                bk2 = wd[2] * G.prb + wd2[2] * G.prbs
                bk3 = wd[3] * G.prb + wd2[3] * G.prbs
            elif ii == 15 and zd[0][0] >= 25.0:
                bk = wd[0] * G.pro + wd2[0] * G.pros
                bk2 = wd[2] * G.pro + wd2[2] * G.pros
                bk3 = wd[3] * G.pro + wd2[3] * G.pros
            elif ii == 16:
                bk = wd[0] * G.prb + wd2[0] * G.prbs
                bk2 = wd[2] * G.prb + wd2[2] * G.prbs
                bk3 = wd[3] * G.prb + wd2[3] * G.prbs
            else:
                if zd[0][0] > 1.0e-6:
                    # 原本は `if(ii == 9)` と `else` の中身が同じ
                    d = std_min(zd[0][0], 25.0)
                    bk = (wd[0] * G.prb + wd2[0] * G.prbs) * 25.0 / d
                    bk2 = (wd[2] * G.prb + wd2[2] * G.prbs) * 25.0 / d
                    bk3 = (wd[3] * G.prb + wd2[3] * G.prbs) * 25.0 / d
                else:
                    bk = 0.0
                    bk2 = 0.0
                    bk3 = 0.0
        bk = bk * G.hikrate
        bk3 = bk3 * G.hikrate * 0.8
        G.pslr = 1.0

        if kako:
            if G.pslsi == 1 and pszd[0][0] > 1.0e-6:
                G.pslr = std_min(1.0, zd[0][0] / pszd[0][0])
            else:
                G.pslr = 0.0

    elif ii == 17:
        G.tz[1] = zem[0][0] - zem[0][2] - zem[0][3] - zem[0][4]
        G.tz[2] = zem[0][2] + zem[0][3] + zem[0][4]
        bk = wem[0] * G.pro + wem2[0] * G.pros
        bk2 = wem[2] * G.pro + wem2[2] * G.pros
        bk3 = wem[3] * G.pro + wem2[3] * G.pros
        bk = bk * G.hikrate
        bk3 = bk3 * G.hikrate * 0.8
        G.pslr = 1.0

        if kako:
            if G.pslsi == 1 and pszem[0][0] > 1.0e-6:
                G.pslr = std_min(1.0, zem[0][0] / pszem[0][0])
            else:
                G.pslr = 0.0

    return bk, bk2, bk3
