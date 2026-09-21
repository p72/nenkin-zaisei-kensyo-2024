# -*- coding: utf-8 -*-
"""
厚生年金/給付費推計/outhou.cpp の忠実移植（報酬の内訳を書き出す）
==================================================================
59 行。`hou2.{試算番号}_{制度}.csv` に、年齢別の

    ax   標準報酬総額（パートを除く）÷ `ad[k]`（改定率）
    gx   被保険者数（パートを除く）
    a/g  1人あたり標準報酬 ÷ `ad[k]`
    gtal 被保険者数（パートも含む）
    gztal / gntal / getal  継続・新規・受給待期

を7行ずつ出す。確認用のファイルで、他のプログラムは読まない。

`if(true)` で囲んである
-----------------------
```c
if(true) {
  fprintf(fp,"%s\\n", ",k,s,x=15-69,15,16,…");
  …
}
```

常に真なので何も変わらない。旗で切り替えるつもりだった跡と読める
（F9 の仲間）。

見出しが実際の列とずれている
----------------------------
見出しは `,k,s,x=15-69,15,16,…,75` と書いてあるが、書くのは
`FOR(x, 14, 75)` の 62 列。見出しの `x=15-69` の欄に **14歳の値**が入り、
以降1つずれる。`ax[k][14][s]` は `shkehiho()` が
「70歳未満の計」として使っている添字（E27 の隣）なので、
**先頭の列は年齢ではなく計**。見出しの `x=15-69` はそれを指している
とも読めるが、そのあとの `15,16,…` が1つずれているのは変わらない。

`tmq` を作る範囲と使う範囲
--------------------------
```c
FOR(x, 14, 75) {
  if(gx.AT(k,x,s) > 0.0) tmq.AT(x) = ax.AT(k,x,s) / gx.AT(k,x,s);
  else                   tmq.AT(x) = 0.0;
}
```

`tmq` は `VEC(double, 75)`（76 要素）で 14〜75 を埋める。
`k` のループの中で毎回作り直すので持ち越しは無い。
"""
from csvio import join
from glva import G
from setconst import KE, KIJUN

__all__ = ["outhou"]


def outhou():
    """outhou.cpp:6 の忠実移植。"""
    pseid = G.pseid
    ax = G.ax
    gx = G.gx

    tmq = [0.0] * 76

    fp = G.fp_map["hou2_out"]

    fp.write("%s\n" % (
        ",k,s,x=15-69,15,16,17,18,19,20,"
        "21,22,23,24,25,26,27,28,29,30,"
        "31,32,33,34,35,36,37,38,39,40,"
        "41,42,43,44,45,46,47,48,49,50,"
        "51,52,53,54,55,56,57,58,59,60,"
        "61,62,63,64,65,66,67,68,69,70,"
        "71,72,73,74,75"))
    for s in range(1, 3 + 1):
        if pseid != 0 and s == 3:
            continue
        for k in range(KIJUN, KE + 1):
            tmp = G.ad[k]
            for x in range(14, 75 + 1):
                if gx[k, x, s] > 0.0:
                    tmq[x] = ax[k, x, s] / gx[k, x, s]
                else:
                    tmq[x] = 0.0

            vals = [ax[k, x, s] / tmp for x in range(14, 75 + 1)]
            fp.write("%s,%d,%d,%s\n"
                     % ("ax", k, s, join(vals, "%19.12f")))
            vals = [gx[k, x, s] for x in range(14, 75 + 1)]
            fp.write("%s,%d,%d,%s\n"
                     % ("gx", k, s, join(vals, "%19.12f")))
            vals = [tmq[x] / tmp for x in range(14, 75 + 1)]
            fp.write("%s,%d,%d,%s\n"
                     % ("a/g", k, s, join(vals, "%19.12f")))

            vals = [G.gtal[k, x, s] for x in range(14, 75 + 1)]
            fp.write("%s,%d,%d,%s\n"
                     % ("gtal", k, s, join(vals, "%19.12f")))

            vals = [G.gztal[k, x, s] for x in range(14, 75 + 1)]
            fp.write("%s,%d,%d,%s\n"
                     % ("gztal", k, s, join(vals, "%19.12f")))

            vals = [G.gntal[k, x, s] for x in range(14, 75 + 1)]
            fp.write("%s,%d,%d,%s\n"
                     % ("gntal", k, s, join(vals, "%19.12f")))

            vals = [G.getal[k, x, s] for x in range(14, 75 + 1)]
            fp.write("%s,%d,%d,%s\n"
                     % ("getal", k, s, join(vals, "%19.12f")))
