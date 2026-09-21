# -*- coding: utf-8 -*-
"""
被保険者推計/simlkyos.c の忠実移植
==================================
共済3制度（国共済・地共済・私学共済）の2号被保険者数を読み込み、
人口推計の終わり（`FJINKOY` = 2120）より後へ伸ばす。

`seido` の対応（`simlkyos.c:25-35`）

    4 → kok（国家公務員共済）
    5 → ren（地方公務員共済。連合会）
    6 → sig（私立学校教職員共済）

やっていること
--------------
1. 制度ごとにファイルを読む（`simlkyos.c:23-58`）。
   **`KIJUNMAP`（2023）より後の年度だけ**取り込む（50-54）。
   実績年度は `readdata.c` の map から入っているので上書きしない。
2. `FJINKOY` より後を、総人口に対する割合の伸びで延ばす（60-101）。

       割合 = Σ 人数 / 総人口
       TMR  = FJINKOY の割合 / FJINKOY-1 の割合      伸び率
       以降  割合[年度] = 割合[年度-1] × TMR
       人数[年度] = 人数[FJINKOY] × (割合[年度]×総人口[年度])
                                   / (割合[FJINKOY]×総人口[FJINKOY])

3. 70歳以上を69歳に寄せる（104-113）
4. 女（性2）を有配偶（性3）・無配偶（性4）に、男（性1）と足して
   男女計（性0）を作る（115-132）

原本の癖をそのまま残しているところ
----------------------------------
1. **割った分母が条件で見ているものと違う**（`simlkyos.c:118-126`）

   ```c
   if ( koyou_j_m[1][y][2][n] + koyou_j_m[2][y][2][n] > 0.0 ) {
     kounen[seido][y][3][n] = kounen[seido][y][2][n]
                              * koyou_j_m[1][y][3][n]
                              / koyou_j_m[1][y][2][n] ;   /* ← [1] だけ */
   ```

   条件は `[1] + [2] > 0` なのに、割るのは `[1]` だけ。`[1] == 0` で
   `[2] > 0` なら**ゼロ除算**になる（inf か nan）。同梱データでは
   `[1]`（正規雇用者）が 0 になる年齢が無いので起きない。
   （`検証/原本の不具合.md`）

2. **`sojinko_wari` を `FJINKOY-1` から 0 で埋める**
   （`simlkyos.c:62-64`）。`FJINKOY-1` と `FJINKOY` は直後に上書き
   されるので、実際に効くのは `FJINKOY+1` 以降。

3. **`TMP * sojinko_c[…] * sojinko_c[…] > 0.0` で3つ掛けて判定**
   （`simlkyos.c:72`）。どれかが 0 なら偽になるという書き方。
   あふれる心配は無い（人数と総人口なので 10^8 程度）。
   偽のときは `TMR` が 0.0 のままなので、`FJINKOY+1` 以降の割合が
   すべて 0 になる。

4. **`ENDY > FJINKOY` が偽なら2の段が丸ごと飛ぶ**（`simlkyos.c:60`）
   `ENDY`=2150 > `FJINKOY`=2120 なので常に真。

5. **`printf` と `fprintf(stderr, …)` の両方に同じ文を出す**
   （`simlkyos.c:93-94`）。補正がゼロのときだけ。
"""
import sys

from cnum import ReadCsv
from fopn import P
from glva import G
from setconst import ENDY, KIJUNMAP, NY, STARTY

__all__ = ["simlkyos"]


def simlkyos():
    """simlkyos.c:12 の忠実移植。"""
    buf = [0.0] * 130
    kounen = G.kounen
    sc = G.sojinko_c
    kjm = G.koyou_j_m
    SJINKOY, FJINKOY = G.SJINKOY, G.FJINKOY

    for seido in range(4, 7):
        G.seido = seido
        path = P.kyos(seido, G.JIN, G.QX, G.NC)
        try:
            fp = ReadCsv(path)
        except OSError:
            print("共済からのデータファイルを開けません!", file=sys.stderr)
            raise SystemExit(2)
        fp.karayomi()
        # ---- 1. 読む。simlkyos.c:41-56 ----
        for sei in range(1, 3):
            G.sei = sei
            for _ in range(SJINKOY, FJINKOY + 1):
                fp.read_csv(buf)
                if buf[0] + 3 != seido:
                    print(f"共済{seido}２号データのseido番号と整合性が"
                          "取れません", file=sys.stderr)
                    raise SystemExit(2)
                ii = int(buf[1])
                jj = int(buf[2])
                if jj > KIJUNMAP:
                    for nenrei in range(15, 101):
                        kounen[seido, jj - STARTY, ii, nenrei] = buf[nenrei - 11]

        # ---- 2. FJINKOY より後へ延ばす。simlkyos.c:60-101 ----
        if ENDY > FJINKOY:
            TMP = 0.0
            TMQ = 0.0
            TMR = 0.0
            sw = [0.0] * NY          # double sojinko_wari[ENDY-STARTY+1]
            for nendo in range(FJINKOY - 1, ENDY + 1):
                sw[nendo - STARTY] = 0.0
            for sei in range(1, 3):
                for nenrei in range(15, 101):
                    TMP += (kounen[seido, FJINKOY - 1 - STARTY, sei,
                                        nenrei])
                    TMQ += (kounen[seido, FJINKOY - STARTY, sei, nenrei])

            f1 = FJINKOY - 1 - STARTY
            f0 = FJINKOY - STARTY
            if TMP * (sc[f1, 0]) * (sc[f0, 0]) > 0.0:
                sw[f1] = TMP / (sc[f1, 0])
                sw[f0] = TMQ / (sc[f0, 0])
                TMR = sw[f0] / sw[f1]

            for nendo in range(FJINKOY + 1, ENDY + 1):
                sw[nendo - STARTY] = sw[nendo - 1 - STARTY] * TMR

            for nendo in range(FJINKOY + 1, ENDY + 1):
                y = nendo - STARTY
                den = sw[f0] * (sc[f0, 0])
                for sei in range(1, 3):
                    for nenrei in range(15, 101):
                        if den > 0.0:
                            kounen[seido, y, sei, nenrei] = (
                                (kounen[seido, f0, sei, nenrei])
                                * (sw[y] * (sc[y, 0])) / den)
                        else:
                            if sei == 1 and nenrei == 15:
                                msg = (f"共済 {seido} の {nendo:04d} 年度の"
                                       "補正がゼロです")
                                print(msg)
                                print(msg, file=sys.stderr)
                            kounen[seido, y, sei, nenrei] = 0.0

    # ---- 3. 70歳以上を69歳に寄せる。simlkyos.c:104-113 ----
    for seido in range(4, 7):
        G.seido = seido
        for nendo in range(STARTY, ENDY + 1):
            y = nendo - STARTY
            for sei in range(1, 3):
                for nenrei in range(70, 101):
                    kounen[seido, y, sei, 69] += kounen[seido, y, sei, nenrei]
                    kounen[seido, y, sei, nenrei] = 0.0

    # ---- 4. 性別の割り振り。simlkyos.c:115-132 ----
    for seido in range(4, 7):
        G.seido = seido
        for nendo in range(STARTY, ENDY):
            y = nendo - STARTY
            for nenrei in range(15, 101):
                # 癖 1.：条件は [1]+[2] なのに割るのは [1] だけ
                if ((kjm[1, y, 2, nenrei])
                        + (kjm[2, y, 2, nenrei])) > 0.0:
                    kounen[seido, y, 3, nenrei] = (
                        (kounen[seido, y, 2, nenrei])
                        * (kjm[1, y, 3, nenrei])
                        / (kjm[1, y, 2, nenrei]))
                    kounen[seido, y, 4, nenrei] = (
                        (kounen[seido, y, 2, nenrei])
                        * (kjm[1, y, 4, nenrei])
                        / (kjm[1, y, 2, nenrei]))
                kounen[seido, y, 0, nenrei] = (
                    (kounen[seido, y, 1, nenrei])
                    + (kounen[seido, y, 2, nenrei]))
