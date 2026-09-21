# -*- coding: utf-8 -*-
"""
厚生年金/給付費推計/rousaki.cpp の忠実移植（老齢先充てへの振り替え）
=====================================================================
94 行。80〜114歳の**遺族厚生年金**のうち、在職支給率が足元より
下がったぶん（`sik[KIJUN][x][s3][11][1] - sik[k][x][s3][11][1]`）を
**老齢厚生年金（`i` = 1〜4）へ振り替える**。

「老先」（ろうさき）は「老齢を先に充てる」ことで、遺族厚生年金は
老齢厚生年金との差額だけ出す（併給調整）という扱い。

    d3x[k][x][ss][i][jj] += dtemp * sinrou[ss][i] / rtemp
    d3 [k][ss][i][jj][2] += 同じ

`jj` の付け替え
---------------
```c
FOR(j, 1, 58) {
  int jj = -1;
  if(j == 1 || j == 7  || j == 13 || j == 35 || j == 41) jj = j;
  if(j == 5 || j == 11 || j == 17 || j == 39 || j == 45) jj = j - 2;
  if(jj < 0) continue;
```

`d3` の列 1・7・13・35・41 はそのまま、5・11・17・39・45 は
**2つ手前の列へ**振り替える（5 → 3、11 → 9、17 → 15、…）。
遺族の列を老齢の列に読み替えている。

`sinrou` — 振り替え先の按分
---------------------------
```c
FOR(i, 1, 4) FOR(s, 1, 3) {
  …
  FOR(j, 7, 10) {
    sinrou.AT(s, 0) += d3xs.AT(k, x, s, i, j) * (1.0 - sik.AT(k, x, s3, i, 1));
    sinrou.AT(s, i) += d3xs.AT(k, x, s, i, j) * (1.0 - sik.AT(k, x, s3, i, 1));
  }
}
```

老齢の 1〜4 それぞれに、在職で止まっているぶん（`1 - sik`）を
重みにして配る。合計が 0 のときは

```c
if (sinrou.AT(1, 0) + sinrou.AT(3, 0) <= 0.0){ sinrou.AT(1,0)=1.0; sinrou.AT(1,1)=1.0; }
if (sinrou.AT(2, 0) <= 0.0){ sinrou.AT(2,0)=1.0; sinrou.AT(2,1)=1.0; }
```

と 1.0 を入れて 0 割りを避ける。**`i = 1` にだけ全部寄せる**形になる。

`FOR(s, 1, 3)` がグローバルの `s` を隠す
----------------------------------------
`_extension.h` の `FOR` は `for(int s = …)` と展開するので、
この関数の中の `s` は**局所変数**。グローバルの `s`（種別）は
変わらない。移植版も局所変数にする。

男女の振り替え先が入れ替わる
----------------------------
```c
FOR(ss, 1, 3) {
  if(pseid != 0 && ss == 3) continue;
  if((s == 2 && ss == 2) || (s != 2 && ss != 2)) continue;
```

遺族の `s` が女（2）なら振り替え先 `ss` は男（1 か 3）、
`s` が男なら `ss` は女（2）。遺族年金を受けるのは配偶者だから。
"""
from glva import G
from setconst import KE, KIJUN

__all__ = ["rousaki"]

# `d3` の列の付け替え（そのまま / 2つ手前へ）
_JJ_SAME = (1, 7, 13, 35, 41)
_JJ_MINUS2 = (5, 11, 17, 39, 45)


def rousaki():
    """rousaki.cpp:7 の忠実移植。"""
    pseid = G.pseid
    d3 = G.d3
    d3x = G.d3x
    d3xs = G.d3xs
    sik = G.sik
    rc = G.rc

    # 原本は VEC(double, 3, 4) の局所配列
    sinrou = [[0.0] * 5 for _ in range(4)]

    for k in range(KIJUN + 1, KE + 1):
        for x in range(80, 114 + 1):
            if not (x >= 66 + k - 7 and x <= 95 + k - KIJUN):
                continue

            for a in range(1, 3 + 1):
                for b in range(0, 4 + 1):
                    sinrou[a][b] = 0.0

            for i in range(1, 4 + 1):
                for s in range(1, 3 + 1):   # グローバルの s を隠す
                    if pseid != 0 and s == 3:
                        continue
                    if s != 2:
                        s3 = 1
                    else:
                        s3 = 2
                    for j in range(7, 10 + 1):
                        sinrou[s][0] += (d3xs[k, x, s, i, j]
                                         * (1.0 - sik[k, x, s3, i, 1]))
                        sinrou[s][i] += (d3xs[k, x, s, i, j]
                                         * (1.0 - sik[k, x, s3, i, 1]))
            if sinrou[1][0] + sinrou[3][0] <= 0.0:
                sinrou[1][0] = 1.0
                sinrou[1][1] = 1.0
            if sinrou[2][0] <= 0.0:
                sinrou[2][0] = 1.0
                sinrou[2][1] = 1.0

            for j in range(1, 58 + 1):
                if j in _JJ_SAME:
                    jj = j
                elif j in _JJ_MINUS2:
                    jj = j - 2
                else:
                    continue

                for s in range(1, 3 + 1):
                    if pseid != 0 and s == 3:
                        continue
                    if s != 2:
                        s3 = 1
                    else:
                        s3 = 2
                    rtemp = (sik[KIJUN, x, s3, 11, 1]
                             - sik[k, x, s3, 11, 1])
                    if rtemp < 0.0:
                        rtemp = 0.0

                    if jj == j:
                        dtemp = d3xs[k, x, s, 11, j] * rtemp
                    else:
                        dtemp = (d3xs[k, x, s, 11, j] * rtemp
                                 * (1.0 - rc[s, k, x]))

                    if dtemp <= 0.0:
                        continue

                    for ss in range(1, 3 + 1):
                        if pseid != 0 and ss == 3:
                            continue
                        if ((s == 2 and ss == 2)
                                or (s != 2 and ss != 2)):
                            continue
                        if ss != 3:
                            kk = G.ee[1]
                        else:
                            kk = G.ee[2]
                        if ss != 2:
                            rtemp2 = sinrou[1][0] + sinrou[3][0]
                        else:
                            rtemp2 = sinrou[2][0]

                        for i in range(1, 4 + 1):
                            d3x[k, x, ss, i, jj] += (dtemp * sinrou[ss][i]
                                                     / rtemp2)
                            d3[k, ss, i, jj, 2] += (dtemp * sinrou[ss][i]
                                                    / rtemp2)
                            if jj == 13 and (i == 1 or i == 3):
                                d3x[k, x, ss, i, 26] += (
                                    dtemp * sinrou[ss][i] / rtemp2 * kk)
                                d3[k, ss, i, 26, 2] += (
                                    dtemp * sinrou[ss][i] / rtemp2 * kk)
                            elif jj == 15 and (i == 1 or i == 3):
                                d3x[k, x, ss, i, 27] += (
                                    dtemp * sinrou[ss][i] / rtemp2 * kk)
                                d3[k, ss, i, 27, 2] += (
                                    dtemp * sinrou[ss][i] / rtemp2 * kk)
