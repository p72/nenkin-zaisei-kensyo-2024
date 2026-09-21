# -*- coding: utf-8 -*-
"""
基礎年金/printout.c の忠実移植（結果ファイル kekka*.csv）
==========================================================
`main.c` から2回呼ばれる。`cut_ba == 0` が調整前（`kekka…b.csv`）、
`cut_ba == 1` が調整後（`kekka…a.csv`）。

書くもの
--------
    試算番号 / カット終了年度 / 最終カット率
    基礎年金給付費（新法＋旧法／新法／基礎年金交付金）    各 106 行
    基礎年金拠出金・同（国庫）・拠出金算定対象者
    特別国庫負担内訳 / 独自給付費等 / 経済前提
    妻積（各制度への分配額）
    収支見通し（25 項目 × 106 行）

`cut_ba == 0` のときだけ積立金を計算し直す
------------------------------------------
```c
Tumitate[nendo] = Tumitate[nendo-1] * 運用利回り
   + ( 収入 − 支出 ) * pow( 運用利回り , 1/2 ) ;
```

収入と支出を年度の真ん中に置くので、利回りの平方根を掛ける。
`cut_ba == 1` のときは `tyousei()` が最後に置いた値をそのまま使う。

国年の積立金が尽きる年度
------------------------
`Tumitate` が負になる最初の年度を `fp_out[OUTPUT]`（`output.csv`）に
書く。`cut_ba == 1 && CUT_KOTEI == 0` なら `kekka…a.csv` にも
「国年が○年度に枯渇しました」と出す。尽きなければ
`S_C_NENDO`（マクロ経済スライドの終了年度）を書く。

原本の癖をそのまま残しているところ
----------------------------------
1. **見出しの1行目で `head[i]` を渡しているのに書式に `%s` が無い**
   （`printout.c:412`）。`fprintf( fp , "," , head[i] )` なので
   **`","` だけが出る**。1行目は「収入」「支出」「その他」の位置を
   示すだけの行になっている。（`検証/原本の不具合.md`）

2. **`fclose( fp_out[OUTPUT] )` が2回呼ばれる。**`printout()` が
   2回呼ばれるので、2回目は閉じたストリームへの書き込みと二重クローズ
   になる。glibc ではヒープが壊れて落ちるので、移植パッチで
   コメントアウトしてある（`検証/実行/patches/glibc-portability.patch`）。
   閉じないぶんはプロセス終了時のフラッシュで書かれる。

3. **`outfile` が初期化されない。**`cut_ba` が 0 でも 1 でもなければ
   未初期化の値を `fp_out[]` の添字に使う。呼ばれるのは 0 と 1 だけ。

4. **`kokatu_nendo` を探すループが `SAISHUNENDO - 5` で止まる。**
   2121〜2125年度に尽きても見つけない。

5. **「最終カット率」を出すのは `cut_ba == 1 && CUT_KOTEI == 0 &&
   kako == 0` のときだけ。**それ以外は空欄。

6. **`shinkyu = SUM` の見出しが「基礎年金給付費（新法＋旧法）」、
   `OLD` が「基礎年金交付金」。**旧法ぶんは交付金として扱う。

7. **収支見通しの行末が `",\n"`。**25 項目ぜんぶに `,` を付けた
   あと、さらに `,` を1つ足して改行する。列が1つ多く見える。
"""
import math

from glva import G
from setconst import (
    ECON_SHONENDO, FUKA, IZOKU, KEKKA_a, KEKKA_b, KOKUNEN, KOUNEN,
    NENREI_SUM, NEW, NOUFU, OLD, OLD_MENJO, OLD_NOUFU,
    OUTPUT, PROVIDE, SAISHUNENDO, SHIGAKU, SHONENDO, SUM,
    TOKUBETU_20MAE, TUMATUMI_NENDO, UNDER_63, UNDER_67,
)

__all__ = ["printout"]

_J0 = NENREI_SUM - NENREI_SUM       # 年齢計の置き場（= 0）

# 収支見通しの項目名（`printout.c:384`）
_HEAD = (
    "保険料月額", "保険料収入（国年）", "保険料収入（付加年金）", "運用収入",
    "国庫（基礎年金）", "国庫（特別国庫）",
    "国庫（死亡一時金付加分）", "国庫（付加年金）", "国庫（旧法寡婦年金免除分）",
    "住宅融資債権", "妻積み", "こども子育て特別会計から繰入", "収入合計",
    "支出合計", "死亡一時金納付分", "死亡一時金付加分",
    "新法寡婦年金", "旧法寡婦年金免除分以外", "旧法寡婦年金免除分", "付加年金",
    "基礎年金拠出金", "基礎年金拠出金（特別国庫）", "業務勘定への繰入",
    "年度末積立金", "保険料改定率",
)
_SHUNYU_CNT = 13
_SHISHUTU_CNT = 10
_SONOTA_CNT = 2

_SEIDO_HEAD = ",制度計,国年,厚年,国共,地共,私学"


def printout(cut_ba):
    """printout.c:17 の忠実移植。"""
    ny = SAISHUNENDO - SHONENDO + 1
    # 原本の `double Temp_Ichijikin[106][3]` / `Temp_Kafu[106][4]`
    Temp_Ichijikin = [[0.0] * 3 for _ in range(ny)]
    Temp_Kafu = [[0.0] * 4 for _ in range(ny)]

    if cut_ba == 0:
        outfile = KEKKA_b

        for nendo in range(SHONENDO, SAISHUNENDO + 1):
            sn = nendo - SHONENDO
            Temp_Ichijikin[sn][SUM] = G.Ichijikin[sn][SUM]
            Temp_Ichijikin[sn][NOUFU] = G.Ichijikin[sn][NOUFU]
            Temp_Ichijikin[sn][FUKA] = G.Ichijikin[sn][FUKA]

            Temp_Kafu[sn][SUM] = G.Kafu[sn][SUM]
            Temp_Kafu[sn][NEW] = G.Kafu[sn][NEW]
            Temp_Kafu[sn][OLD_NOUFU] = G.Kafu[sn][OLD_NOUFU]
            Temp_Kafu[sn][OLD_MENJO] = G.Kafu[sn][OLD_MENJO]

        for nendo in range(G.KAISHI1, SAISHUNENDO + 1):
            sn = nendo - SHONENDO
            ir = G.interest_rate[nendo - ECON_SHONENDO]
            G.Tumitate[sn] = (
                G.Tumitate[sn - 1] * ir
                + (G.Hokenryou_y[sn] + G.Fuka_Hokenryou_y[sn]
                   + G.Kyoshutukin_Kokko[KOKUNEN][sn][_J0][SUM]
                   + G.Tumatumi[KOKUNEN][nendo - TUMATUMI_NENDO]
                   + G.Yuushi_Saiken[sn]
                   + G.Kodomo_Noufukin[sn]
                   - G.Kyoshutukin[KOKUNEN][sn][_J0][SUM]
                   - G.Ichijikin[sn][NOUFU] - G.Ichijikin[sn][FUKA] * 3. / 4.
                   - G.Kafu[sn][NEW] - G.Kafu[sn][OLD_NOUFU]
                   - G.Fuka[sn][SUM] * 3. / 4.
                   - G.Fukushi[sn])
                * math.pow(ir, 1. / 2.))
    elif cut_ba == 1:
        outfile = KEKKA_a

        for nendo in range(SHONENDO, SAISHUNENDO + 1):
            sn = nendo - SHONENDO
            Temp_Ichijikin[sn][SUM] = G.Ichijikin_Cut[sn][SUM]
            Temp_Ichijikin[sn][NOUFU] = G.Ichijikin_Cut[sn][NOUFU]
            Temp_Ichijikin[sn][FUKA] = G.Ichijikin_Cut[sn][FUKA]

            Temp_Kafu[sn][SUM] = G.Kafu_Cut[sn][SUM]
            Temp_Kafu[sn][NEW] = G.Kafu_Cut[sn][NEW]
            Temp_Kafu[sn][OLD_NOUFU] = G.Kafu_Cut[sn][OLD_NOUFU]
            Temp_Kafu[sn][OLD_MENJO] = G.Kafu_Cut[sn][OLD_MENJO]
    else:
        raise RuntimeError("printout: cut_ba は 0 か 1（原本は未初期化の "
                           "outfile を使う）")

    fp = G.fp_out[outfile]
    w = fp.write

    w("試算番号,")
    w("%s-%s" % (G.Version, G.Version_cut))
    if cut_ba == 0:
        w("b\n")
    elif cut_ba == 1:
        w("a\n")

    # ---- 国年が枯渇する年度（癖 4.） ----
    kokatu_nendo = -1
    for nendo in range(G.KAISHI1 - 1, SAISHUNENDO - 4):
        if G.Tumitate[nendo - SHONENDO] < 0.:
            kokatu_nendo = nendo
            G.fp_out[OUTPUT].write("%d," % kokatu_nendo)
            break

    w("カット終了年度,")
    if cut_ba == 1 and G.CUT_KOTEI == 0:
        if kokatu_nendo == -1:
            w("%d\n" % G.S_C_NENDO)
        else:
            print("国年が%d年度に枯渇しました" % kokatu_nendo)
            w("国年が%d年度に枯渇しました\n" % kokatu_nendo)
    else:
        w("\n")

    w("最終カット率,")
    if cut_ba == 1 and G.CUT_KOTEI == 0 and G.kako == 0:
        n = G.S_C_NENDO if kokatu_nendo == -1 else kokatu_nendo
        w("%20.14e\n" % G.cut_ruiseki[n - ECON_SHONENDO][n - ECON_SHONENDO]
          [UNDER_63 - NENREI_SUM])
    else:
        w("\n")

    w("\n")
    w("\n")
    # 癖 2. ここで fp_out[OUTPUT] を閉じない

    # ---- 基礎年金給付費 ----
    for shinkyu in range(SUM, OLD + 1):
        if shinkyu == SUM:
            w("基礎年金給付費（新法＋旧法）\n")
        elif shinkyu == NEW:
            w("基礎年金給付費（新法）\n")
        elif shinkyu == OLD:
            w("基礎年金交付金\n")

        w(",合計,,,,,")
        w(",老齢,,,,,")
        w(",障害,,,,,")
        w(",遺族,,,,,\n")

        w(_SEIDO_HEAD * 4 + "\n")

        for nendo in range(SHONENDO, SAISHUNENDO + 1):
            sn = nendo - SHONENDO
            out = ["%15d" % nendo]
            for kubun in range(SUM, IZOKU + 1):
                for seido in range(SUM, SHIGAKU + 1):
                    out.append(",%20.14e"
                               % G.Kyufu[seido][sn][_J0][shinkyu][kubun][SUM]
                               [SUM])
            out.append("\n")
            w("".join(out))

    # ---- 基礎年金拠出金 ----
    w("基礎年金拠出金\n")
    w(",単価,合計,国年,厚年,国共,地共,私学\n")

    for nendo in range(SHONENDO, SAISHUNENDO + 1):
        sn = nendo - SHONENDO
        out = ["%15d," % nendo, "%20.14e," % G.Tanka[sn][_J0][SUM]]
        for seido in range(SUM, SHIGAKU + 1):
            out.append("%20.14e," % G.Kyoshutukin[seido][sn][_J0][SUM])
        out.append("\n")
        w("".join(out))

    # ---- 基礎年金拠出金（国庫） ----
    w("基礎年金拠出金（国庫）\n")
    w(",単価,国庫負担割合(年度末),合計,国年,厚年,国共,地共,私学,")
    w("合計,老齢,障害,遺族\n")

    for nendo in range(SHONENDO, SAISHUNENDO + 1):
        sn = nendo - SHONENDO
        out = ["%15d," % nendo,
               "%20.14e," % G.Tanka_Kokko[sn][_J0][SUM],
               "%20.14e," % G.Kokko_Wariai[nendo - (SHONENDO - 1)]]
        for seido in range(SUM, SHIGAKU + 1):
            out.append("%20.14e," % G.Kyoshutukin_Kokko[seido][sn][_J0][SUM])
        for kubun in range(SUM, IZOKU + 1):
            out.append("%20.14e,"
                       % G.Kokko[SUM][sn][_J0][SUM][kubun][SUM])
        out.append("\n")
        w("".join(out))

    # ---- 拠出金算定対象者 ----
    w("拠出金算定対象者\n")
    w(",合計,１号,")
    w("厚年２号,厚年３号,国共２号,国共３号,地共２号,地共３号,私学２号,私学３号,")
    w("産休免除者（１号再掲）,育休免除者（１号再掲）,付加納付者（１号再掲）\n")

    for nendo in range(SHONENDO, SAISHUNENDO + 1):
        sn = nendo - SHONENDO
        out = ["%15d," % nendo,
               "%20.14e," % G.SanteiTaishou[SUM][sn][SUM],
               "%20.14e," % G.SanteiTaishou[KOKUNEN][sn][1]]
        for seido in range(KOUNEN, SHIGAKU + 1):
            for goubetu in range(2, 4):
                out.append("%20.14e," % G.SanteiTaishou[seido][sn][goubetu])
        out.append("%20.14e," % G.Sankyu_Taishou[sn])
        out.append("%20.14e," % G.Ikukyu_Taishou[sn])
        out.append("%20.14e," % G.Fuka_Ninzu[sn])
        out.append("\n")
        w("".join(out))

    # ---- 特別国庫負担内訳 ----
    w("特別国庫負担内訳\n")
    w(",合計,免除,嵩上げ（納付）,嵩上げ（免除）,老福下支え,５年年金,２０歳前\n")

    for nendo in range(SHONENDO, SAISHUNENDO + 1):
        sn = nendo - SHONENDO
        out = ["%15d," % nendo]
        for shurui in range(SUM, TOKUBETU_20MAE + 1):
            out.append("%20.14e," % G.Tokubetukokko[sn][_J0][shurui][SUM])
        out.append("\n")
        w("".join(out))

    # ---- 独自給付費等 ----
    w("独自給付費等\n")
    w(",死亡一時金納付分,死亡一時金付加分,")
    w("新法寡婦年金,旧法寡婦年金免除分以外,旧法寡婦年金免除分,付加年金,")
    w("１号被保険者数,保険料収入（国年）,保険料収入（付加年金）,")
    w("住宅融資債権,業務勘定への繰入,こども子育て特別会計から繰入\n")

    for nendo in range(SHONENDO, SAISHUNENDO + 1):
        sn = nendo - SHONENDO
        w("".join((
            "%d," % nendo,
            "%20.14e," % Temp_Ichijikin[sn][NOUFU],
            "%20.14e," % Temp_Ichijikin[sn][FUKA],
            "%20.14e," % Temp_Kafu[sn][NEW],
            "%20.14e," % Temp_Kafu[sn][OLD_NOUFU],
            "%20.14e," % Temp_Kafu[sn][OLD_MENJO],
            "%20.14e," % G.Fuka[sn][SUM],
            "%20.14e," % G.Hiho_Kokunen[sn],
            "%20.14e," % G.Hokenryou_y[sn],
            "%20.14e," % G.Fuka_Hokenryou_y[sn],
            "%20.14e," % G.Yuushi_Saiken[sn],
            "%20.14e," % G.Fukushi[sn],
            "%20.14e" % G.Kodomo_Noufukin[sn],
            "\n")))

    # ---- 経済前提 ----
    w("経済前提\n")
    w(",物価上昇率,賃金上昇率,運用利回り,")
    w("改定率（マクロ込み、67歳）,改定率（マクロ込み、68歳）,"
      "改定率（マクロ込み、88歳）,")
    w("特別調整率（67歳）,特別調整率（68歳）,特別調整率（88歳）\n")

    for nendo in range(ECON_SHONENDO, SAISHUNENDO + 1):
        ei = nendo - ECON_SHONENDO
        w("".join((
            "%d," % nendo,
            "%20.14e," % G.cpi_up[ei],
            "%20.14e," % G.base_up[ei],
            "%20.14e," % G.interest_rate[ei],
            "%20.14e," % G.kaiteiritu[ei][UNDER_67 - UNDER_67],
            "%20.14e," % G.kaiteiritu[ei][68 - UNDER_67],
            "%20.14e," % G.kaiteiritu[ei][88 - UNDER_67],
            "%20.14e," % G.T[ei][UNDER_67 - UNDER_67],
            "%20.14e," % G.T[ei][68 - UNDER_67],
            "%20.14e" % G.T[ei][88 - UNDER_67],
            "\n")))

    # ---- 妻積（各制度への分配額） ----
    w("妻積（各制度への分配額）\n")
    w(",国年,厚年,国共,地共,私学,妻積残額,国年積立金\n")

    w("%d（原価）," % (TUMATUMI_NENDO - 1))
    w("%20.14e," % 0.)
    for _seido in range(KOUNEN, SHIGAKU + 1):
        w("%20.14e," % 0.)
    w("%20.14e\n" % G.Tumatumi_2014[SUM])

    for nendo in range(SHONENDO, SAISHUNENDO + 1):
        out = ["%d," % nendo]
        for seido in range(KOKUNEN, SHIGAKU + 1):
            out.append("%20.14e," % G.Tumatumi[seido][nendo - TUMATUMI_NENDO])
        out.append("%20.14e," % G.Tumatumi[SUM][nendo - TUMATUMI_NENDO])
        out.append("%20.14e" % G.Tumitate[nendo - SHONENDO])
        out.append("\n")
        w("".join(out))

    w("\n")

    # ---- 収支見通し ----
    w("\n")
    w("収支見通し\n")

    n_all = _SHUNYU_CNT + _SHISHUTU_CNT + _SONOTA_CNT

    w(",")
    for i in range(0, n_all):
        if i == 0:
            w("収入")
        elif i == _SHUNYU_CNT:
            w("支出")
        elif i == _SHUNYU_CNT + _SHISHUTU_CNT:
            w("その他")
        w(",")              # 癖 1. head[i] は出ない
    w("\n")

    w("年度,")
    for i in range(0, n_all):
        w("%s," % _HEAD[i])
    w("\n")

    for nendo in range(SHONENDO, SAISHUNENDO + 1):
        sn = nendo - SHONENDO

        if nendo == SHONENDO:
            tumitateunyou = 0.
        else:
            ir = G.interest_rate[nendo - ECON_SHONENDO]
            tumitateunyou = (
                G.Tumitate[sn - 1] * (ir - 1)
                + (G.Hokenryou_y[sn] + G.Fuka_Hokenryou_y[sn]
                   + G.Kyoshutukin_Kokko[KOKUNEN][sn][_J0][SUM]
                   + G.Tumatumi[KOKUNEN][nendo - TUMATUMI_NENDO]
                   + G.Yuushi_Saiken[sn]
                   + G.Kodomo_Noufukin[sn]
                   - G.Kyoshutukin[KOKUNEN][sn][_J0][SUM]
                   - G.Fuka[sn][SUM] * 3. / 4.
                   - Temp_Ichijikin[sn][NOUFU]
                   - Temp_Ichijikin[sn][FUKA] * 3. / 4.
                   - Temp_Kafu[sn][NEW] - Temp_Kafu[sn][OLD_NOUFU]
                   - G.Fukushi[sn])
                * (math.pow(ir, 1. / 2.) - 1))

        shunyu = (
            G.Hokenryou_y[sn] + G.Fuka_Hokenryou_y[sn] + tumitateunyou
            + G.Kyoshutukin_Kokko[KOKUNEN][sn][_J0][SUM]
            + G.Tokubetukokko[sn][_J0][SUM][SUM]
            + Temp_Ichijikin[sn][FUKA] / 4. + G.Fuka[sn][SUM] / 4.
            + Temp_Kafu[sn][OLD_MENJO]
            + G.Yuushi_Saiken[sn] + G.Tumatumi[KOKUNEN][nendo - TUMATUMI_NENDO]
            + G.Kodomo_Noufukin[sn])

        shishutu = (
            Temp_Ichijikin[sn][NOUFU] + Temp_Ichijikin[sn][FUKA]
            + Temp_Kafu[sn][NEW] + Temp_Kafu[sn][OLD_NOUFU]
            + Temp_Kafu[sn][OLD_MENJO]
            + G.Fuka[sn][SUM]
            + G.Kyoshutukin[KOKUNEN][sn][_J0][SUM]
            + G.Tokubetukokko[sn][_J0][SUM][SUM]
            + G.Fukushi[sn])

        w("".join((
            "%d," % nendo,
            "%20.14e," % G.Hokenryou_m[sn][0],
            "%20.14e," % G.Hokenryou_y[sn],
            "%20.14e," % G.Fuka_Hokenryou_y[sn],
            "%20.14e," % tumitateunyou,
            "%20.14e," % G.Kyoshutukin_Kokko[KOKUNEN][sn][_J0][SUM],
            "%20.14e," % G.Tokubetukokko[sn][_J0][SUM][SUM],
            "%20.14e," % (Temp_Ichijikin[sn][FUKA] / 4.),
            "%20.14e," % (G.Fuka[sn][SUM] / 4.),
            "%20.14e," % Temp_Kafu[sn][OLD_MENJO],
            "%20.14e," % G.Yuushi_Saiken[sn],
            "%20.14e," % G.Tumatumi[KOKUNEN][nendo - TUMATUMI_NENDO],
            "%20.14e," % G.Kodomo_Noufukin[sn],
            "%20.14e," % shunyu,
            "%20.14e," % shishutu,
            "%20.14e," % Temp_Ichijikin[sn][NOUFU],
            "%20.14e," % Temp_Ichijikin[sn][FUKA],
            "%20.14e," % Temp_Kafu[sn][NEW],
            "%20.14e," % Temp_Kafu[sn][OLD_NOUFU],
            "%20.14e," % Temp_Kafu[sn][OLD_MENJO],
            "%20.14e," % G.Fuka[sn][SUM],
            "%20.14e," % G.Kyoshutukin[KOKUNEN][sn][_J0][SUM],
            "%20.14e," % G.Tokubetukokko[sn][_J0][SUM][SUM],
            "%20.14e," % G.Fukushi[sn],
            "%20.14e," % G.Tumitate[sn],
            "%20.14e," % G.kakaku[nendo - ECON_SHONENDO],
            ",\n")))          # 癖 7.

    fp.close()
    G.fp_out[outfile] = None

    # ---- provide ファイル（調整期間一致のときだけ） ----
    if cut_ba == 0 and G.TOUGOU == 1:
        fpp = G.fp_out[PROVIDE]
        pw = fpp.write
        pw("年度,保険料収入,一時金付加分国庫,付加年金国庫,"
           "その他収入（融資債権）,その他収入（妻積）\n")
        for nendo in range(SHONENDO, SAISHUNENDO + 1):
            sn = nendo - SHONENDO
            pw("%d," % (nendo - 2000))
            pw("%20.14e," % (G.Hokenryou_y[sn] + G.Fuka_Hokenryou_y[sn]
                             + G.Kodomo_Noufukin[sn]))
            pw("%20.14e," % (G.Ichijikin[sn][FUKA] / 4))
            pw("%20.14e," % (G.Fuka[sn][SUM] / 4))
            pw("%20.14e," % G.Yuushi_Saiken[sn])
            pw("%20.14e," % G.Tumatumi[KOKUNEN][nendo - TUMATUMI_NENDO])
            pw("\n")
        pw("\n")

        pw("独自給付費等（年度間値）\n")
        pw("年度,一時金納付分,一時金付加分,付加年金,")
        pw("業務勘定への繰入\n")
        for nendo in range(SHONENDO, SAISHUNENDO + 1):
            sn = nendo - SHONENDO
            pw("%d," % (nendo - 2000))
            pw("%20.14e," % G.Ichijikin[sn][NOUFU])
            pw("%20.14e," % G.Ichijikin[sn][FUKA])
            pw("%20.14e," % G.Fuka[sn][SUM])
            pw("%20.14e\n" % G.Fukushi[sn])
        pw("\n")

        pw("独自給付費等（年度末値）\n")
        pw("年度,新法寡婦年金\n")
        for nendo in range(SHONENDO, SAISHUNENDO + 1):
            sn = nendo - SHONENDO
            pw("%d," % (nendo - 2000))
            pw("%20.14e\n" % G.Kafu_Nendomatu[sn][NEW])
        pw("\n")

    return
