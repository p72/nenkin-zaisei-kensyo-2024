# -*- coding: utf-8 -*-
"""
被保険者推計/readdata.c の忠実移植
==================================
入力CSVを17本読んでグローバル配列に入れる。計算はしない。

読む順（`readdata.c` の上から）
------------------------------
 1. 出力先のディレクトリを `mkdir` し、エラー用ファイルを開く
 2. 人口（性別1,2）→ `sojinko_c`, `jinko_c`
 3. 人口割合 → `jinko_wari[1..4]`
 4. 女性有配偶割合（推計）→ `yuhaig_r`
 5. 労働力率（ケース毎）→ `roud_r`（STARTY〜ROUDYR）
 6. 就業率（ケース毎）→ `syugyo_r`（同）
 7. 雇用者割合（実績）→ `koyou_r`（STARTY〜ENDY）
 8. 正規雇用者割合 → `seiki_hiseiki_r[1]`（STARTY〜ROUDYR）
 9. 非正規フル → `seiki_hiseiki_r[2]`（同）
10. 非正規短時間 → `seiki_hiseiki_r[3]`（同）
11. 諸設定値 → `hiseiki_tan_r_all`, `heikinh_c[1..9]`,
    `hiseiki_jikan_r[1..4]`, `kounenteki_c[1..6]`
12. 被保険者数（map）→ `kounen`, `sangou`, `ichigou`, `partnin[..][0][0][0]`
13. 1号有配偶率 → `ichiyuhaigr`
14. 1・3号の上限年齢 → `xend`（45年化のときだけ読む。それ以外は一律60）
15. 調整率の実績 → `cutritu`
16. パート（現行 / 1段階 / 2段階）→ `kbetu_partkiso[..][..][..][..][1..3]`

`TEMP` を作業領域に使う
-----------------------
5〜10 は `read_roud` が `TEMP` に読み込み、そのあと本体へ写す
（`readdata.c:104-233`）。読むたびに `TEMP` を 0 で埋め直す。
`read_roud` は3ブロック（性別1と2、あと1つ）×年度を読む形で、
`nendo` と `sei` は CSV の1列目・2列目から取る。

原本の癖をそのまま残しているところ
----------------------------------
1. **年度が減ったら読み止める**（`readdata.c:39,66,86`）
   `while ( read_csv(...) != EOF && buffer[0] > previous_buffer0 )` で、
   1列目が前の行より大きい間だけ続ける。CSV の末尾に合計行や空行が
   あっても止まる作りだが、**`previous_buffer0` を更新し忘れている
   ところがある**。人口割合（`readdata.c:66-76`）は
   `previous_buffer0` を更新しないので、2行目以降は
   `buffer[0] > -1000` で必ず真になり、**EOF まで読み続ける**。
   結果は同じ（ファイルが年齢順に並んでいる）。

2. **`read_roud` / `read_map` の中でグローバルを書き換える**
   `nendo` / `sei` / `nenrei` / `seido` はグローバルなので、
   呼び出しから戻ったあとも値が残る。原本は次のループで上書きするので
   影響は無いが、読み解くときに注意が要る。

3. **`read_map` の引数名がグローバルと同じ `nendo`**
   （`readdata.c:462`）。関数の中では引数（局所）が見える。
   `nenrei` と `seido` はグローバルのまま。

4. **`%02d` に4桁の年度を流している**（`readdata.c:274` ほか）
   `sprintf(filename, "…/%02dmap.csv", jj)` の `jj` は 2020〜2023 なので
   `2020map.csv` になる。`%02d` は「最低2桁」なので切り詰めない。
   同梱データのファイル名もそうなっている。

5. **`char filename[250]`**（`readdata.c:16,17`）
   `run_pipeline.sh` が長い絶対パスに書き換えるとあふれるので、
   同スクリプトが `1024` に直している（`検証/原本の不具合.md` C2/C3）。
"""
import sys

from cnum import EOF, ReadCsv
from fopn import P, rslt_dir
from glva import G
from setconst import CNENDO, CUT_JY, DATA_MAX, ENDY, KIJUNMAP, STARTY

__all__ = ["readdata", "read_roud", "read_map"]


def _die(msg):
    print(msg, file=sys.stderr)
    raise SystemExit(2)


def _open(path, what):
    """原本の `if ((fp = fopen(path,"r")) == NULL) { … exit(2); }`。"""
    try:
        return ReadCsv(path)
    except OSError:
        _die(what)


def readdata():
    """readdata.c:10 の忠実移植。"""
    buf = [0.0] * DATA_MAX
    G.previous_buffer0 = -1000.0

    # readdata.c:21-29。出力先を作り、エラー用ファイルを開く
    rslt_dir(G.BANGO)
    try:
        G.fp_err = open(P.err(G.BANGO), "w", encoding="utf-8", newline="")
    except OSError:
        _die("出力用ファイルを開けません")

    # ---- 人口。readdata.c:31-57 ----
    for sei in (1, 2):
        G.sei = sei
        fp = _open(P.pop(sei, G.JIN, G.QX, G.NC),
                   f"性別{sei:01d}, 出生{G.JIN:01d}, 死亡{G.QX:01d}, "
                   f"入国{G.NC:01d}の人口ファイルを開けません!")
        fp.karayomi()
        G.previous_buffer0 = -1000.0
        while True:
            rc, _ = fp.read_csv(buf)
            if rc == EOF or not (buf[0] > G.previous_buffer0):
                break
            ii = int(buf[0])
            jj = int(buf[1])
            if ii < STARTY or ii > ENDY:
                _die("人口ファイルに不適切な年度が入っています!")
            if jj != sei:
                _die("人口ファイルに不適切な性別が入っています!")
            G.sojinko_c[ii - STARTY, jj] = buf[2]
            for nenrei in range(0, 121):
                G.jinko_c[ii - STARTY, jj, nenrei] = buf[nenrei + 3]
            G.previous_buffer0 = buf[0]

    # ---- 人口割合。readdata.c:59-77 ----
    # **previous_buffer0 を更新しないので EOF まで読む**（癖 1.）
    fp = _open(P.wari(), "人口割合ファイルを開けません!")
    fp.karayomi()
    G.previous_buffer0 = -1000.0
    while True:
        rc, _ = fp.read_csv(buf)
        if rc == EOF or not (buf[0] > G.previous_buffer0):
            break
        nenrei = int(buf[0])
        if nenrei < 0 or nenrei > 120:
            _die("人口割合ファイルに不適切な年齢が入っています!")
        G.jinko_wari[1, nenrei] = buf[1]
        G.jinko_wari[2, nenrei] = buf[2]
        G.jinko_wari[3, nenrei] = buf[2]
        G.jinko_wari[4, nenrei] = buf[2]

    # ---- 女性有配偶割合（推計）。readdata.c:79-102 ----
    fp = _open(P.yuhaigr(), "女性有配偶割合 (推計) ファイルを開けません!")
    fp.karayomi()
    G.previous_buffer0 = -1000.0
    while True:
        rc, _ = fp.read_csv(buf)
        if rc == EOF or not (buf[0] > G.previous_buffer0):
            break
        ii = int(buf[0])
        jj = int(buf[1])
        if ii < STARTY or ii > ENDY:
            _die("女性有配偶 (推計) ファイルに不適切な年度が入っています!")
        if jj != 2:
            _die("女性有配偶 (推計) ファイルに不適切な性別が入っています!")
        for nenrei in range(15, 106):
            G.yuhaig_r[ii - STARTY, nenrei] = buf[nenrei - 12]
        G.previous_buffer0 = buf[0]

    # ---- 労働力率・就業率・雇用者割合ほか。readdata.c:104-233 ----
    # どれも「TEMP を 0 にする → read_roud → 本体へ写す」の3段（癖の TEMP）
    _via_temp(P.roudou(G.ROUDR), "労働力率ファイル (ケース毎) を開けません!",
              G.roud_r, G.ROUDYR)
    _via_temp(P.syugyor(G.ROUDR), "就業率ファイル (ケース毎) を開けません!",
              G.syugyo_r, G.ROUDYR)
    _via_temp(P.koyour(), "雇用者割合ファイル (実績) を開けません!",
              G.koyou_r, ENDY)
    _via_temp(P.seikir(), "正規雇用者割合ファイル (実績) を開けません!",
              G.seiki_hiseiki_r[1], G.ROUDYR)
    _via_temp(P.hiseikifurur(),
              "非正規フル雇用者割合ファイル (実績) を開けません!",
              G.seiki_hiseiki_r[2], G.ROUDYR)
    _via_temp(P.hiseikitanr(),
              "非正規短時間雇用者割合ファイル (実績) を開けません!",
              G.seiki_hiseiki_r[3], G.ROUDYR)

    # ---- 諸設定値。readdata.c:235-271 ----
    fp = _open(P.syosettei(G.ROUDR), "諸設定値ファイル (ケース毎) を開けません!")
    fp.karayomi()
    fp.karayomi()
    for _ in range(STARTY, G.ROUDYR + 1):
        fp.read_csv(buf)
        nendo = int(buf[0])
        kk = int(buf[1])
        if kk != G.ROUDR:
            _die("諸設定値ファイルの内容が労働力率の設定と一致しません!")
        y = nendo - STARTY
        G.hiseiki_tan_r_all[y] = buf[2]
        for ii in range(1, 10):
            G.heikinh_c[ii, y] = buf[ii + 2]
        G.hiseiki_jikan_r[1, y] = buf[12] + buf[13]
        G.hiseiki_jikan_r[2, y] = buf[14]
        G.hiseiki_jikan_r[3, y] = buf[15]
        G.hiseiki_jikan_r[4, y] = buf[16]
        for ii in range(1, 7):
            G.kounenteki_c[ii, y] = buf[ii + 16]

    # ---- 被保険者数（map）。readdata.c:273-293 ----
    for jj in range(STARTY, KIJUNMAP):
        fp = _open(P.map_(jj), f"{jj:02d}年度被保険者数を開けません!")
        read_map(fp, jj)
    fp = _open(P.map_(KIJUNMAP, G.MODE45),
               f"{KIJUNMAP:02d}年度被保険者数を開けません!")
    read_map(fp, KIJUNMAP)

    # ---- 1号有配偶率。readdata.c:295-306 ----
    fp = _open(P.ichiyuhaigr(), "１号有配偶率ファイルを開けません!")
    fp.karayomi()
    for _ in range(20, 70):
        fp.read_csv(buf)
        nenrei = int(buf[0])
        G.ichiyuhaigr[nenrei] = buf[1]

    # ---- 1・3号の上限年齢。readdata.c:308-329 ----
    if G.MODE45 == 1:
        fp = _open(P.ichisanxend(), "１・３号上限年齢ファイルを開けません!")
        fp.karayomi()
        for _ in range(STARTY, 2051):
            fp.read_csv(buf)
            nendo = int(buf[0])
            G.xend[nendo - STARTY] = int(buf[1])
        for nendo in range(2051, ENDY + 1):
            G.xend[nendo - STARTY] = G.xend[nendo - 1 - STARTY]
    else:
        for nendo in range(STARTY, ENDY + 1):
            G.xend[nendo - STARTY] = 60

    # ---- 調整率の実績。readdata.c:331-341 ----
    fp = _open(P.cut_jisseki(), "調整率実績ファイルを開けません!")
    for _ in range(CNENDO, CUT_JY + 1):
        fp.read_csv(buf)
        nendo = int(buf[0])
        G.cutritu[nendo - CNENDO] = buf[1]

    # ---- パート。readdata.c:343-435 ----
    # ykubun 1 が現行、2 が1段階、3 が2段階
    _read_part(P.part0(), "パート入力ファイル (１段階) を開けません!", 1, buf)
    if G.PART >= 1:
        _read_part(P.part1(G.MODE),
                   "パート入力ファイル (１段階) を開けません!", 2, buf)
    if G.PART == 2:
        _read_part(P.part2(G.MODE),
                   "パート入力ファイル（２段階）を開けません!", 3, buf)


def _via_temp(path, ng, dst, yend):
    """`readdata.c:104-233` に6回出てくる「TEMP 経由で読む」形。

    1. `TEMP[STARTY..ENDY][1..4][15..105]` を 0 にする
    2. `read_roud(fp, STARTY, yend)` で読む
    3. `dst[STARTY..yend][1..4][15..105]` に写す

    `yend` は労働力率・就業率・正規・非正規が `ROUDYR`（2040）、
    雇用者割合だけ `ENDY`（`readdata.c:160`）。読む年度と写す年度は
    原本でも常に同じ。
    """
    # 1. TEMP を 0。要素ごとの代入なのでスライスで置き換えてよい
    G.TEMP[:, 1:5, 15:106] = 0.0
    fp = _open(path, ng)
    read_roud(fp, STARTY, yend)
    # 3. 本体へ写す
    n = yend - STARTY + 1
    dst[0:n, 1:5, 15:106] = G.TEMP[0:n, 1:5, 15:106]


def _read_part(path, ng, ykubun, buf):
    """`readdata.c:343-370` に3回出てくる「パートを読む」形。

    1行に18個。並びは (性1/性2) × (pkubun 1,2,7) × (tkubun 1,2,3)。
    `kbetu_partkiso[sei][kubun][pkubun][tkubun][ykubun]` に入れる。
    """
    fp = _open(path, ng)
    fp.karayomi()
    for _ in range(1, 12):
        fp.read_csv(buf)
        ii = int(buf[0])
        k = 1
        for tkubun in (1, 2, 3):
            for sei in (1, 2):
                for pkubun in (1, 2, 7):
                    G.kbetu_partkiso[sei, ii, pkubun, tkubun, ykubun] = buf[k]
                    k += 1


def read_roud(fp, ynendo1, ynendo2):
    """readdata.c:439 の忠実移植。`TEMP` に3ブロック読み込む。

    先頭を1行読み飛ばし、そのあと「2行読み飛ばす＋年度ぶん読む」を3回。
    `nendo` と `sei` は CSV の1列目・2列目から取る（**グローバルを
    書き換える**。癖 2.）。
    """
    buf = [0.0] * DATA_MAX
    fp.karayomi()
    for _ in range(1, 4):
        fp.karayomi()
        fp.karayomi()
        for _ in range(ynendo1, ynendo2 + 1):
            fp.read_csv(buf)
            G.nendo = int(buf[0])
            G.sei = int(buf[1])
            for nenrei in range(15, 106):
                G.nenrei = nenrei
                G.TEMP[G.nendo - STARTY, G.sei, nenrei] = buf[nenrei - 12]


def read_map(fp, nendo):
    """readdata.c:462 の忠実移植。被保険者数の実績を読む。

    **引数 `nendo` がグローバルと同じ名前**（癖 3.）。関数の中では
    引数が見える。`nenrei` と `seido` はグローバルのまま書き換わる。

    1行に13個。`jj` が性別（1, 2）で、年齢は 15〜89。
    """
    buf = [0.0] * DATA_MAX
    y = nendo - STARTY
    fp.karayomi()
    for jj in range(1, 3):
        fp.karayomi()
        fp.karayomi()
        for _ in range(15, 90):
            fp.read_csv(buf)
            n = int(buf[0])
            G.nenrei = n
            G.kounen[2, y, jj, n] = buf[1]
            G.kounen[3, y, jj, n] = buf[2]
            G.kounen[4, y, jj, n] = buf[3]
            G.kounen[5, y, jj, n] = buf[4]
            G.kounen[6, y, jj, n] = buf[5]
            G.partnin[y, jj, n, 0, 0, 0] = buf[6]
            G.kounen[1, y, jj, n] = G.kounen[2, y, jj, n] + G.kounen[3, y, jj, n]
            G.kounen[0, y, jj, n] = (G.kounen[1, y, jj, n]
                                     + G.kounen[4, y, jj, n]
                                     + G.kounen[5, y, jj, n]
                                     + G.kounen[6, y, jj, n])
            G.sangou[1, y, jj, n] = buf[7]
            G.sangou[4, y, jj, n] = buf[8]
            G.sangou[5, y, jj, n] = buf[9]
            G.sangou[6, y, jj, n] = buf[10]
            G.sangou[0, y, jj, n] = (G.sangou[1, y, jj, n]
                                     + G.sangou[4, y, jj, n]
                                     + G.sangou[5, y, jj, n]
                                     + G.sangou[6, y, jj, n])
            G.ichigou[1, y, jj, n] = buf[11]
            G.ichigou[2, y, jj, n] = buf[12]
            G.ichigou[0, y, jj, n] = (G.ichigou[1, y, jj, n]
                                      + G.ichigou[2, y, jj, n])

    # readdata.c:500-513。性別 0（男女計）を作る
    for n in range(15, 90):
        G.nenrei = n
        for seido in range(0, 7):
            G.seido = seido
            G.kounen[seido, y, 0, n] = (G.kounen[seido, y, 1, n]
                                        + G.kounen[seido, y, 2, n])
            G.sangou[seido, y, 0, n] = (G.sangou[seido, y, 1, n]
                                        + G.sangou[seido, y, 2, n])
        for seido in range(0, 3):
            G.seido = seido
            G.ichigou[seido, y, 0, n] = (G.ichigou[seido, y, 1, n]
                                         + G.ichigou[seido, y, 2, n])
        G.partnin[y, 0, n, 0, 0, 0] = (G.partnin[y, 1, n, 0, 0, 0]
                                       + G.partnin[y, 2, n, 0, 0, 0])
