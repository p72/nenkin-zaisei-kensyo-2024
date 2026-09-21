# -*- coding: utf-8 -*-
"""
厚生年金/給付費推計/shkehiho.cpp の忠実移植（被保険者の集計）
==============================================================
228 行。年度 `k`・種別 `s` の**被保険者**を年齢 `x` × 経過年 `t` で
集計する。`shke()` の先頭で1回呼ばれる。

作るもの
--------
| 名前 | 中身 |
|---|---|
| `ap` `ap65` `ap70` `ap75` `ap85` | 被保険者数（それぞれ 65歳以上・70歳以上…の内訳） |
| `appart*` | うちパート（短時間労働者） |
| `a` `a60` `a65` `a70` `a75` `a85` | 標準報酬総額 |
| `aiku` | うち育休産休で保険料免除のぶん |
| `*dum` | 同じ値をもう1本（適用拡大の按分で引く用） |
| `apart` `a60part` … | 適用拡大で新しく入るぶん |
| `ax` `gx` `gtal` `gztal` `gntal` `getal` | 年齢別の報酬総額と人数 |
| `g2` `ge2` … `we2` `g3` `bb3` … | 年度別に取っておく控え |

`ax` `gx` の添字 14 が「計」
---------------------------
```c
if(15 <= x && x <= 75) {
  ax.AT(k, x, s) += g.AT(x, t) * bb.AT(x, t) - gpt.AT(x, t) * bbpt.AT(x, t);
  ...
  if(x < 70) {
    ax.AT(k, 14, s) += g.AT(x, t) * bb.AT(x, t) - gpt.AT(x, t) * bbpt.AT(x, t);
```

`x` のループは 15 から始まるので `ax[k][14][s]` が空いている。
そこを「70歳未満の計」として使っている。同じ行を2回書いて
足しているので、**丸めの入る余地は無いが式が重複している**。

`xend` で 70歳以上を入れるかどうかが変わる
------------------------------------------
`ap` は `x < 70` なら無条件に足し、`x >= 70` は `xend > 70` のときだけ
足す。`sepsd.cpp` が `xend = 90`（厚年）/ `75`（共済）を入れるので、
どちらも 70歳以上を足す。`xend > 85` の枝（`ap85`）は厚年だけ通る。

`tmp` の作り方が年齢で違う
--------------------------
```c
tmp = 0.0;
tmr = 0.0;
if(x >= 20 && x <= 49) {
  tmp = g.AT(x, t) * bb.AT(x, t) * (1.0 - ikucoe.AT(k, x));
  tmr = g.AT(x, t) * bb.AT(x, t) * ikucoe.AT(k, x);
} else if (flg_hiho70 == 0 && x < 70) {
  tmp = g.AT(x, t) * bb.AT(x, t);
}
```

20〜49歳は育休産休の取得率で2つに分ける。**50〜69歳は
`flg_hiho70 == 0` のときだけ** `tmp` に入り、70歳以上は
`flg_hiho70 == 0` でも 0 のまま。ところが下では

```c
} else {                  /* x >= 70 */
  if(xend > 70) {
    a.AT(k, s2)    += tmp;
```

と 70歳以上でも `a` に足している。**足す値は必ず 0**なので
結果は変わらないが、枝が空振りしている。
`検証/原本の不具合.md` の E27。

`tms` は宣言だけ
---------------
`double tmp, tmq, tmr, tms;` の `tms` は一度も使われない（F9 の仲間）。
"""
from glva import G

__all__ = ["shkehiho"]


def shkehiho():
    """shkehiho.cpp:4 の忠実移植。"""
    k = G.k
    s = G.s
    s2 = G.s2
    pseid = G.pseid
    xend = G.xend

    g = G.g
    gpt = G.gpt
    bb = G.bb
    bbpt = G.bbpt

    kou2 = (pseid == 0 and s <= 2)

    for x in range(15, 85 + 1):
        for t in range(0, 70 + 1):

            G.gee[k, s2, x, t] = g[x, t]
            G.geept[k, s2, x, t] = gpt[x, t]

            if x < 70:
                G.ap[k, s2] += g[x, t]
                G.apdum[k, s2] += g[x, t]
                if kou2:
                    G.appart[k, s2] += gpt[x, t]
                    G.appartdum[k, s2] += gpt[x, t]
            elif x >= 70:
                if xend > 70:
                    G.ap[k, s2] += g[x, t]
                    G.apdum[k, s2] += g[x, t]
                    if kou2:
                        G.appart[k, s2] += gpt[x, t]
                        G.appartdum[k, s2] += gpt[x, t]

            if 65 <= x <= 69:
                G.ap65[k, s2] += g[x, t]
                G.ap65dum[k, s2] += g[x, t]
                if kou2:
                    G.appart65[k, s2] += gpt[x, t]
                    G.appart65dum[k, s2] += gpt[x, t]

            if xend > 70 and x >= 70:
                G.ap70[k, s2] += g[x, t]
                G.ap70dum[k, s2] += g[x, t]
                if kou2:
                    G.appart70[k, s2] += gpt[x, t]
                    G.appart70dum[k, s2] += gpt[x, t]

            if xend > 75 and x >= 75:
                G.ap75[k, s2] += g[x, t]
                G.ap75dum[k, s2] += g[x, t]
                if kou2:
                    G.appart75[k, s2] += gpt[x, t]
                    G.appart75dum[k, s2] += gpt[x, t]

            if xend > 85 and x >= 85:
                G.ap85[k, s2] += g[x, t]
                G.ap85dum[k, s2] += g[x, t]
                if kou2:
                    G.appart85[k, s2] += gpt[x, t]
                    G.appart85dum[k, s2] += gpt[x, t]

            tmp = 0.0
            tmr = 0.0
            if 20 <= x <= 49:
                tmp = g[x, t] * bb[x, t] * (1.0 - G.ikucoe[k, x])
                tmr = g[x, t] * bb[x, t] * G.ikucoe[k, x]
            elif G.flg_hiho70 == 0 and x < 70:
                tmp = g[x, t] * bb[x, t]

            if x < 65:
                G.a[k, s2] += tmp
                G.adum[k, s2] += tmp
                G.aiku[k, s2] += tmr
                G.aikudum[k, s2] += tmr
            elif 65 <= x < 70:
                if xend > 65:
                    G.a[k, s2] += tmp
                    G.adum[k, s2] += tmp
            else:
                # x >= 70 では tmp が必ず 0（E27）
                if xend > 70:
                    G.a[k, s2] += tmp
                    G.adum[k, s2] += tmp

            if 15 <= x <= 75:
                G.ax[k, x, s] += (g[x, t] * bb[x, t]
                                  - gpt[x, t] * bbpt[x, t])
                G.gx[k, x, s] += g[x, t] - gpt[x, t]
                if x < 70:
                    # 添字 14 は「70歳未満の計」（x のループは 15 から）
                    G.ax[k, 14, s] += (g[x, t] * bb[x, t]
                                       - gpt[x, t] * bbpt[x, t])
                    G.gx[k, 14, s] += g[x, t] - gpt[x, t]
                G.gtal[k, x, s] += g[x, t]
                G.gztal[k, x, s] += G.gz[x, t]
                G.gntal[k, x, s] += G.gn[x, t]
                G.getal[k, x, s] += G.ge[x, t]

            if x < 70:
                if x >= 60:
                    G.a60[k, s2] += tmp
                    G.a60dum[k, s2] += tmp
                if x >= 65:
                    G.a65[k, s2] += tmp
                    G.a65dum[k, s2] += tmp
            elif x >= 70 and xend > 70:
                G.a60[k, s2] += tmp
                G.a65[k, s2] += tmp
                G.a70[k, s2] += tmp
                G.a60dum[k, s2] += tmp
                G.a65dum[k, s2] += tmp
                G.a70dum[k, s2] += tmp
                if x >= 75 and xend > 75:
                    G.a75[k, s2] += tmp
                    G.a75dum[k, s2] += tmp
                if x >= 85 and xend > 85:
                    G.a85[k, s2] += tmp
                    G.a85dum[k, s2] += tmp

        # ---- 適用拡大の按分（2024年10月の51人以上）----
        if kou2 and (k == G.partyr3 - 1 or k == G.partyr3):
            tmq = G.dmpt2[k, x, s] * G.ad[k]
            if 20 <= x <= 49:
                tmp = G.lpt1[k, s, x] * tmq * (1.0 - G.ikucoe[k, x])
                tmr = G.lpt1[k, s, x] * tmq * G.ikucoe[k, x]
            else:
                tmp = G.lpt1[k, s, x] * tmq
                tmr = 0.0
            G.apart[k, s] += tmp
            G.aikupart[k, s] += tmr
            if x >= 60:
                G.a60part[k, s] += tmp
            if x >= 65:
                G.a65part[k, s] += tmp
            if x >= 70:
                G.a70part[k, s] += tmp
            if x >= 75:
                G.a75part[k, s] += tmp
            if x >= 85:
                G.a85part[k, s] += tmp

            if k == G.partyr3:
                # `adum` `aikudum` は s2、`a60dum` 以下は s。添字が違う
                G.adum[k, s2] -= tmp
                G.aikudum[k, s2] -= tmr
                if x >= 60:
                    G.a60dum[k, s] -= tmp
                if x >= 65:
                    G.a65dum[k, s] -= tmp
                if x >= 70:
                    G.a70dum[k, s] -= tmp
                if x >= 75:
                    G.a75dum[k, s] -= tmp
                if x >= 85:
                    G.a85dum[k, s] -= tmp

        # ---- オプションの適用拡大 ----
        if (G.flg_part >= 1 and kou2
                and (k == G.partyr4 - 1 or k == G.partyr4)):
            tmq = G.dmpt2[k, x, s] * G.ad[k]
            lsum = (G.lpt2[k, s, x] + G.lpt3[k, s, x] + G.lpt4[k, s, x])
            if 20 <= x <= 49:
                tmp = lsum * tmq * (1.0 - G.ikucoe[k, x])
                tmr = lsum * tmq * G.ikucoe[k, x]
            else:
                tmp = lsum * tmq
                tmr = 0.0
            G.apart[k, s] += tmp
            G.aikupart[k, s] += tmr
            if x >= 60:
                G.a60part[k, s] += tmp
            if x >= 65:
                G.a65part[k, s] += tmp
            if x >= 70:
                G.a70part[k, s] += tmp
            if x >= 75:
                G.a75part[k, s] += tmp
            if x >= 85:
                G.a85part[k, s] += tmp

            if k == G.partyr4:
                G.adum[k, s2] -= tmp
                G.aikudum[k, s2] -= tmr
                if x >= 60:
                    G.a60dum[k, s] -= tmp
                if x >= 65:
                    G.a65dum[k, s] -= tmp
                if x >= 70:
                    G.a70dum[k, s] -= tmp
                if x >= 75:
                    G.a75dum[k, s] -= tmp
                if x >= 85:
                    G.a85dum[k, s] -= tmp

        # ---- 年度別の控え ----
        if x <= 70:
            G.g3[k, s2, x, 0:71] = g[x, 0:71]
            if pseid == 0 and s2 <= 2:
                G.gnp3[k, s2, x, 0:71] = g[x, 0:71] - gpt[x, 0:71]
                G.gpt3[k, s2, x, 0:71] = gpt[x, 0:71]
            G.bb3[k, s2, x, 0:71] = bb[x, 0:71]
            if pseid == 0 and s2 <= 2:
                G.bbnp3[k, s2, x, 0:71] = G.bbnp[x, 0:71]
                G.bbpt3[k, s2, x, 0:71] = bbpt[x, 0:71]

        G.g2[k, s2, x, 0:71] = g[x, 0:71]
        G.ge2[k, s2, x, 0:71] = G.ge[x, 0:71]
        G.gz2[k, s2, x, 0:71] = G.gz[x, 0:71]
        G.gn2[k, s2, x, 0:71] = G.gn[x, 0:71]
        G.gez2[k, s2, x, 0:71] = G.gez[x, 0:71]

        G.bb2[k, s2, x, 0:71] = bb[x, 0:71]
        G.z2[k, s2, x, 0:71] = G.z[x, 0:71, 0, 4]
        G.ze2[k, s2, x, 0:71] = G.ze[x, 0:71, 0, 4]
        G.w2[k, s2, x, 0:71] = G.w[x, 0:71, 0, 4, 0]
        G.we2[k, s2, x, 0:71] = G.we[x, 0:71, 0, 4, 0]
