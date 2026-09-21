# -*- coding: utf-8 -*-
"""
厚生年金/給付費推計/crshfl.cpp の忠実移植（⑤収支計算と⑥分布推計へ渡す）
=========================================================================
230 行。②の**主な出力**を4つのファイルに書く。

| ファイル | 読む先 | 中身 |
|---|---|---|
| `shus.{試算}_{制度}` | ⑤収支計算 | 経済的要素、被保険者数、標準報酬総額、給付費（`d3x`）、拠出金の算定対象（`kfprx`） |
| `shusg.{試算}_{制度}` | ⑤ | `gee` `geept`（年齢×経過年の被保険者） |
| `bunpu_bb.{試算}_{制度}.csv` | ⑥分布推計 | `bb3` `bbnp3` `bbpt3`（標準報酬） |
| `bunpu_g.{試算}_{制度}.csv` | ⑥ | `g3` `gnp3` `gpt3`（被保険者数） |

見出しと列数が合っていない
--------------------------
```c
fprintf(fp, "%s\\n", "AIKU");
fprintf(fp, "%s\\n", "K,S=0,S=1,S=2,S=3");        /* 5 列ぶん */
FOR(k, FLKS, FLKE) {
  seq::print_int(fp, k);
  FOR(s, 0, 3) seq::add_dbl(fp, "%21.14e", aiku.AT(k,s));    /* 4 */
  FOR(s, 1, 3) seq::add_dbl(fp, "%21.14e", aikudum.AT(k,s)); /* +3 */
  seq::line_feed(fp);
}
```

`AIKU` の見出しは5列だが、書くのは **8列**（`k` ＋ `aiku` 4 ＋
`aikudum` 3）。`AP` `A` の方は見出しに `APDUM` `ADUM` が入っていて
数も合っているので、`AIKU` だけ見出しを直し忘れたと読める。
`検証/原本の不具合.md` の F19。⑤は列の位置で読むので影響しない。

`PARTHOU` の見出しが `partyr4` のぶんに付かない
----------------------------------------------
```c
FOR(k, KS, KE) {
  if(pseid == 0 && k == partyr3) {
    fprintf(fp, "%s\\n", "PARTHOU");
    fprintf(fp, "%s\\n", "K,S=0,S=1,S=2,S=3");
    …24列を書く…
  }
  if(flg_part >= 1 && pseid == 0 && k == partyr4) {
    …見出し無しで24列を書く…
  }
}
```

見出しは `partyr3` の側だけ。`flg_part >= 1` のときは
`partyr4` の行が見出し無しで続く。ここも見出しは5列で中身は24列。

`GEE` と `GEEPT` で書式が違う
----------------------------
```c
FOR(t, 0 ,70) vals.push_back(gee.AT(k,s,x,t));
fprintf(fpg, "%d,%s\\n", x, csv::join("%21.14e", vals).c_str());
…
FOR(t, 0, 70) vals.push_back(geept.AT(k,s,x,t));
fprintf(fpg, "%d,%s\\n", x, csv::join("%21.16e", vals).c_str());
```

`gee` は `%21.14e`、`geept` は **`%21.16e`**（2桁多い）。
`%21.16e` は幅 21 に収まらないので、実際には 23 文字になる
（`-1.2345678901234567e+08`）。⑤は `atof` で読むので影響しない。

`bbpt3` だけ年度の上限が違う
----------------------------
```c
FOR(k, KIJUN, KE) … bbnp3 …
FOR(k, KIJUN, 70) … bbpt3 …     /* KE ではなく 70 */
```

`bbpt3`（パートの標準報酬）は **2070年度まで**しか書かない。
`bunpu_g` の方は `gpt3` も `KE` まで書く。⑥分布推計が
`bbpt` をどこまで読むか次第だが、⑥の入力としては
2071年度以降が欠ける。同 F20。
"""
from csvio import add_dbl, join, line_feed, print_int
from glva import G
from setconst import FLKE, FLKS, KE, KIJUN, KS

__all__ = ["crshfl"]


def crshfl():
    """crshfl.cpp:9 の忠実移植。"""
    pseid = G.pseid
    d3x = G.d3x
    kfprx = G.kfprx

    fp = G.fp_map["sh"]

    fp.write("%d,%d\n" % (KS, KE))
    fp.write("%s\n" % "経済的要素")
    fp.write("%s\n" % ("年度,利回り,賃金,物価,年金改定率(比例),"
                       "年金改定率(加給),年金改定率(基礎),年金改定率(物価)"))
    for k in range(1, KE + 1):
        fp.write("%d,%8.5f,%8.5f,%8.5f,%8.5f,%8.5f,%8.5f,%8.5f\n"
                 % (k, G.ri[k], G.h[k], G.ci[k], G.hh[k],
                    G.hp2[k, 67], G.hp2[k, 67], G.ci2[k, 67]))

    fp.write("%s\n" % ",AP,,,,APDUM")
    fp.write("%s\n" % "K,S=0,S=1,S=2,S=3,S=1,S=2,S=3")
    for k in range(FLKS, FLKE + 1):
        print_int(fp, k)
        for s in range(0, 3 + 1):
            add_dbl(fp, "%21.14e", G.ap[k, s])
        for s in range(1, 3 + 1):
            add_dbl(fp, "%21.14e", G.apdum[k, s])
        line_feed(fp)

    if G.flg_hiho70 == 0:
        fp.write("%s\n" % ",AP65,,,,AP70,,,,AP75")
        fp.write("%s\n" % ("K,S=0,S=1,S=2,S=3,S=0,S=1,S=2,S=3,"
                           "S=0,S=1,S=2,S=3"))
        for k in range(FLKS, FLKE + 1):
            print_int(fp, k)
            for s in range(0, 3 + 1):
                add_dbl(fp, "%21.14e", G.ap65[k, s])
            for s in range(0, 3 + 1):
                add_dbl(fp, "%21.14e", G.ap70[k, s])
            for s in range(0, 3 + 1):
                add_dbl(fp, "%21.14e", G.ap75[k, s])
            line_feed(fp)

    if G.flg_hiho70 == 0:
        fp.write("%s\n" % ",A,,,,ADUM,,,A60,,,,A65,,,,A70,,,,A75")
        fp.write("%s\n" % ("k,s=0,s=1,s=2,s=3,s=1,s=2,s=3,s=0,s=1,s=2,s=3,"
                           "s=0,s=1,s=2,s=3,s=0,s=1,s=2,s=3,"
                           "s=0,s=1,s=2,s=3"))
        for k in range(FLKS, FLKE + 1):
            print_int(fp, k)
            for s in range(0, 3 + 1):
                add_dbl(fp, "%21.14e", G.a[k, s])
            for s in range(1, 3 + 1):
                add_dbl(fp, "%21.14e", G.adum[k, s])
            for s in range(0, 3 + 1):
                add_dbl(fp, "%21.14e", G.a60[k, s])
            for s in range(0, 3 + 1):
                add_dbl(fp, "%21.14e", G.a65[k, s])
            for s in range(0, 3 + 1):
                add_dbl(fp, "%21.14e", G.a70[k, s])
            for s in range(0, 3 + 1):
                add_dbl(fp, "%21.14e", G.a75[k, s])
            line_feed(fp)

    # 見出しは5列だが中身は8列（F19）
    fp.write("%s\n" % "AIKU")
    fp.write("%s\n" % "K,S=0,S=1,S=2,S=3")
    for k in range(FLKS, FLKE + 1):
        print_int(fp, k)
        for s in range(0, 3 + 1):
            add_dbl(fp, "%21.14e", G.aiku[k, s])
        for s in range(1, 3 + 1):
            add_dbl(fp, "%21.14e", G.aikudum[k, s])
        line_feed(fp)

    fp.write("%s\n" % "AAL")
    fp.write("%s\n" % "K,S=0,S=1,S=2,S=3")
    for k in range(FLKS, FLKE + 1):
        print_int(fp, k)
        for s in range(0, 3 + 1):
            add_dbl(fp, "%21.14e", G.aal[k, s])
        line_feed(fp)

    for k in range(KS, KE + 1):
        if pseid == 0 and k == G.partyr3:
            fp.write("%s\n" % "PARTHOU")
            fp.write("%s\n" % "K,S=0,S=1,S=2,S=3")
            if G.flg_hiho70 == 0:
                print_int(fp, k)
                for s in range(0, 3 + 1):
                    add_dbl(fp, "%21.14e", G.apart[k, s])
                for s in range(0, 3 + 1):
                    add_dbl(fp, "%21.14e", G.aikupart[k, s])
                for s in range(0, 3 + 1):
                    add_dbl(fp, "%21.14e", G.a60part[k, s])
                for s in range(0, 3 + 1):
                    add_dbl(fp, "%21.14e", G.a65part[k, s])
                for s in range(0, 3 + 1):
                    add_dbl(fp, "%21.14e", G.a70part[k, s])
                for s in range(0, 3 + 1):
                    add_dbl(fp, "%21.14e", G.a75part[k, s])
                line_feed(fp)
        if G.flg_part >= 1 and pseid == 0 and k == G.partyr4:
            # 見出し無しで続く
            if G.flg_hiho70 == 0:
                print_int(fp, k)
                for s in range(0, 3 + 1):
                    add_dbl(fp, "%21.14e", G.apart[k, s])
                for s in range(0, 3 + 1):
                    add_dbl(fp, "%21.14e", G.aikupart[k, s])
                for s in range(0, 3 + 1):
                    add_dbl(fp, "%21.14e", G.a60part[k, s])
                for s in range(0, 3 + 1):
                    add_dbl(fp, "%21.14e", G.a65part[k, s])
                for s in range(0, 3 + 1):
                    add_dbl(fp, "%21.14e", G.a70part[k, s])
                for s in range(0, 3 + 1):
                    add_dbl(fp, "%21.14e", G.a75part[k, s])
                line_feed(fp)

    if G.nenbeex == 0:
        xstrt = G.xa - 1
    else:
        xstrt = G.xa

    for x in range(xstrt, G.xb + 1):
        for s in range(1, 3 + 1):
            fp.write("%s,%d,%d\n" % ("D3X(k;s;i;0)", x, s))
            fp.write("%s\n" % "k,合計,老退,老在,通退,通在,障害,遺族")
            for k in range(FLKS, FLKE + 1):
                vals = [
                    d3x[k, x, s, 0, 0],
                    d3x[k, x, s, 1, 0] + d3x[k, x, s, 5, 0],
                    d3x[k, x, s, 2, 0] + d3x[k, x, s, 6, 0],
                    d3x[k, x, s, 3, 0] + d3x[k, x, s, 7, 0],
                    d3x[k, x, s, 4, 0] + d3x[k, x, s, 8, 0],
                    d3x[k, x, s, 9, 0] + d3x[k, x, s, 10, 0],
                    (d3x[k, x, s, 11, 0] + d3x[k, x, s, 12, 0]
                     + d3x[k, x, s, 13, 0]),
                ]
                fp.write("%d,%s\n" % (k, join(vals, "%21.14e")))

    for x in range(xstrt, G.xb + 1):
        for s in range(0, 3 + 1):
            for i in range(0, 13 + 1):
                fp.write("%s,%d,%d,%d\n" % ("D3X", x, s, i))
                fp.write("%s\n"
                         % "K,J=25,J=7,J=8,J=9,J=10,J=11,J=12,KOFU")
                for k in range(FLKS, FLKE + 1):
                    vals = [d3x[k, x, s, i, 25]]
                    for j in range(7, 12 + 1):
                        vals.append(d3x[k, x, s, i, j])
                    vals.append(d3x[k, x, s, i, 22] + d3x[k, x, s, i, 23]
                                + d3x[k, x, s, i, 24])
                    vals.append(d3x[k, x, s, i, 22] + d3x[k, x, s, i, 24])
                    vals.append(d3x[k, x, s, i, 23])
                    fp.write("%d,%s\n" % (k, join(vals, "%21.14e")))

    for x in range(xstrt, G.xb + 1):
        for i in range(0, 13 + 1):
            fp.write("%s,%d,%d\n" % ("KFPRX", x, i))
            fp.write("%s\n" % "K,(S-J)=0-1,0-2,1-1,1-2,2-1,2-2,3-1,3-2")
            for k in range(FLKS, FLKE + 1):
                vals = []
                for s in range(0, 3 + 1):
                    for j in range(1, 2 + 1):
                        vals.append(kfprx[k, x, s, i, j])
                fp.write("%d,%s\n" % (k, join(vals, "%21.14e")))

    if G.key == 11:
        fpg = G.fp_map["shg"]

        for k in range(FLKS, FLKE + 1):
            for s in range(0, 3 + 1):
                fpg.write("%s,%s,%d,%s,%d\n"
                          % ("GEE(K,S,X,T)", "K=", k, "S=", s))
                for x in range(15, 85 + 1):
                    vals = [G.gee[k, s, x, t] for t in range(0, 70 + 1)]
                    fpg.write("%d,%s\n" % (x, join(vals, "%21.14e")))

        for k in range(FLKS, FLKE + 1):
            for s in range(0, 3 + 1):
                fpg.write("%s,%s,%d,%s,%d\n"
                          % ("GEEPT(K,S,X,T)", "K=", k, "S=", s))
                for x in range(15, 85 + 1):
                    vals = [G.geept[k, s, x, t] for t in range(0, 70 + 1)]
                    # `gee` は %21.14e だがこちらは %21.16e
                    fpg.write("%d,%s\n" % (x, join(vals, "%21.16e")))

    if G.key == 11:
        fp_bb = G.fp_map["bunpu_bb"]
        fp_bb.write("%s,%s,%s,%s\n" % ("bb", "k", "s", "x"))
        for k in range(KIJUN, KE + 1):
            for s in range(1, 3 + 1):
                for x in range(15, 69 + 1):
                    vals = [G.bb3[k, s, x, t] for t in range(0, 70 + 1)]
                    fp_bb.write("%s,%d,%d,%d,%s\n"
                                % ("bb", k, s, x, join(vals, "%21.14e")))
        if pseid == 0:
            for k in range(KIJUN, KE + 1):
                for s in range(1, 2 + 1):
                    for x in range(15, 69 + 1):
                        vals = [G.bbnp3[k, s, x, t]
                                for t in range(0, 70 + 1)]
                        fp_bb.write("%s,%d,%d,%d,%s\n"
                                    % ("bbnp", k, s, x,
                                       join(vals, "%21.14e")))
            # `bbpt3` だけ上限が KE ではなく 70（F20）
            for k in range(KIJUN, 70 + 1):
                for s in range(1, 2 + 1):
                    for x in range(15, 69 + 1):
                        vals = [G.bbpt3[k, s, x, t]
                                for t in range(0, 70 + 1)]
                        fp_bb.write("%s,%d,%d,%d,%s\n"
                                    % ("bbpt", k, s, x,
                                       join(vals, "%21.14e")))

    if G.key == 11:
        fp_bb = G.fp_map["bunpu_g"]
        fp_bb.write("%s,%s,%s,%s\n" % ("g", "k", "s", "x"))
        for k in range(KIJUN, KE + 1):
            for s in range(1, 3 + 1):
                for x in range(15, 69 + 1):
                    vals = [G.g3[k, s, x, t] for t in range(0, 70 + 1)]
                    fp_bb.write("%s,%d,%d,%d,%s\n"
                                % ("g", k, s, x, join(vals, "%21.14e")))
        if pseid == 0:
            for k in range(KIJUN, KE + 1):
                for s in range(1, 2 + 1):
                    for x in range(15, 69 + 1):
                        vals = [G.gnp3[k, s, x, t]
                                for t in range(0, 70 + 1)]
                        fp_bb.write("%s,%d,%d,%d,%s\n"
                                    % ("gnp", k, s, x,
                                       join(vals, "%21.14e")))
            for k in range(KIJUN, KE + 1):
                for s in range(1, 2 + 1):
                    for x in range(15, 69 + 1):
                        vals = [G.gpt3[k, s, x, t]
                                for t in range(0, 70 + 1)]
                        fp_bb.write("%s,%d,%d,%d,%s\n"
                                    % ("gpt", k, s, x,
                                       join(vals, "%21.14e")))
