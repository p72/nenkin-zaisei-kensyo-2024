# -*- coding: utf-8 -*-
"""
基礎年金/ReadKokunen_jisseki.c の忠実移植（③国民年金の出力を読む）
====================================================================
`KISONENKIN{国年番号}-{経済}-{外枠}` を読んで、国年の受給者数を
`Rorei_New` などに入れる。**1行ずつ「期待どおりの見出しか」を確かめ、
違えば `exit(1)`** という作りなので、行の順番がそのまま仕様になっている。

1年度ぶんの並び（`nenrei` 63〜115 ごとに6ブロック × 性別2行）
--------------------------------------------------------------
    年度,1,年齢,1,1,性別,…   新法老齢基礎年金   → Rorei_New / FurikaeKasan
    年度,1,年齢,1,2,性別,…   新法障害基礎年金   → Shogai_New / FurikaeKasan
    年度,1,年齢,1,3,性別,…   新法遺族基礎年金   → Izoku_New
    年度,1,年齢,2,1,性別,…   旧法老齢・通老年金 → Rorei_Old
    年度,1,年齢,2,2,性別,…   旧法障害年金       → Shogai_Old
    年度,1,年齢,2,3,性別,…   旧法遺族年金       → Izoku_Old

そのあと年度ごとに

    年度,拠出金算定対象者数,…,産休免除者,育休免除者   → SanteiTaishou[1][…][1]
    （6行読み捨て）

読んだ値には `hosei_shin` / `hosei_kyu`（`dtst()` が実績から作った補正率）
を掛ける。

原本の癖をそのまま残しているところ
----------------------------------
1. **`else if( sotai_nendo >= 0 )` の条件が常に真。**`sotai_nendo` は
   `nendo - SHONENDO` で `nendo` は `SHONENDO` から回るので 0 以上。
   つまり見出しが合わなければ必ず `exit(1)`。
   （`検証/原本の不具合.md`）

2. **旧法老齢の列が `ReadHiyousha` と2つずれる。**こちらは
   `buffer[6..11]` を NOUFU / MENJO / KASANOUFU / KASAMENJO /
   ROFUKU_SHITASASAE / GONEN に入れるが、`ReadHiyousha` は
   `buffer[6..13]` を8つ（KAKYU_NOUFU・KAKYU_MENJO を挟む）に入れる。
   国年には加給年金が無いため。列数が違うファイルを同じ配列に入れる。

3. **`SanteiTaishou[…][1] += buffer[1]` を2回続けて足す。**
   ```c
   SanteiTaishou[KOKUNEN][sotai_nendo][1] += buffer[1] ;
   SanteiTaishou[KOKUNEN][sotai_nendo][1] += buffer[2] ;
   ```
   `=` でなく `+=` なので、同じ年度を2回読むと二重になる。1回しか
   読まないので実害は無い。

4. **6行の読み捨てで戻り値だけ見て中身を捨てる。**`if( ... != EOF ) { }`
   と空のブロック。

5. **読み捨てた6行のあとも `buffer` に値が残る。**`read_data` は
   読み切った個数までしか書かないので、次の年度の先頭行で
   列数が足りなければ前の行の値を拾う（`cnum.Buffer` で再現）。
"""
import sys

from cnum import Buffer
from glva import G
from setconst import (
    GONEN, HATACHIMAE, IPPAN, IZOKU, KAKYU, KASAMENJO, KASANOUFU, KIHON,
    KOKUNEN, MAX_JUKYU, MENJO, MENJO_KOUHAN, MENJO_ZENHAN, NENREI_SUM,
    NOUFU, ONNA, OTOKO, ROFUKU_SHITASASAE, ROREI, SAISHUNENDO, SHOGAI,
    SHONENDO, UNDER_63,
)

__all__ = ["ReadKokunen_jisseki"]


def _readerror_jisseki(i):
    print("国民年金ファイルの入力中にエラーが発生しました。エラー箇所は %d" % i)
    sys.exit(1)


def _ng(where):
    print("正常に読めていません 読込箇所は%s" % where)
    sys.exit(1)


def ReadKokunen_jisseki():
    """ReadKokunen_jisseki.c:17 の忠実移植。"""
    fp = G.fp_in[KOKUNEN]
    buffer = Buffer()          # 呼び出し側の `double buffer[DATA_MAX]`

    fp.read_headder()

    for nendo in range(SHONENDO, SAISHUNENDO + 1):
        sn = nendo - SHONENDO

        for nenrei in range(UNDER_63, MAX_JUKYU + 1):
            j = nenrei - NENREI_SUM

            # ---- 新法老齢基礎年金 ----
            for seibetu in range(OTOKO, ONNA + 1):
                rc, _ = fp.read_data(buffer)
                if rc == -1:
                    _readerror_jisseki(1)
                if not (buffer[0] == nendo and buffer[1] == 1
                        and buffer[2] == nenrei and buffer[3] == 1
                        and buffer[4] == 1 and buffer[5] == seibetu):
                    _ng("新法老齢基礎年金")
                h = G.hosei_shin[ROREI][sn]
                G.Rorei_New[KOKUNEN][sn][j][seibetu][NOUFU] = buffer[6] * h
                G.Rorei_New[KOKUNEN][sn][j][seibetu][MENJO_ZENHAN] = \
                    buffer[7] * h
                G.Rorei_New[KOKUNEN][sn][j][seibetu][MENJO_KOUHAN] = \
                    buffer[8] * h
                G.FurikaeKasan[KOKUNEN][sn][j][seibetu][ROREI] = buffer[9] * h

            # ---- 新法障害基礎年金 ----
            for seibetu in range(OTOKO, ONNA + 1):
                rc, _ = fp.read_data(buffer)
                if rc == -1:
                    _readerror_jisseki(2)
                if not (buffer[0] == nendo and buffer[1] == 1
                        and buffer[2] == nenrei and buffer[3] == 1
                        and buffer[4] == 2 and buffer[5] == seibetu):
                    _ng("新法障害基礎年金")
                h = G.hosei_shin[SHOGAI][sn]
                G.Shogai_New[KOKUNEN][sn][j][seibetu][IPPAN][KIHON] = \
                    buffer[6] * h
                G.Shogai_New[KOKUNEN][sn][j][seibetu][IPPAN][KAKYU] = \
                    buffer[7] * h
                G.FurikaeKasan[KOKUNEN][sn][j][seibetu][SHOGAI] = buffer[8] * h
                G.Shogai_New[KOKUNEN][sn][j][seibetu][HATACHIMAE][KIHON] = \
                    buffer[9] * h
                G.Shogai_New[KOKUNEN][sn][j][seibetu][HATACHIMAE][KAKYU] = \
                    buffer[10] * h

            # ---- 新法遺族基礎年金 ----
            for seibetu in range(OTOKO, ONNA + 1):
                rc, _ = fp.read_data(buffer)
                if rc == -1:
                    _readerror_jisseki(3)
                if not (buffer[0] == nendo and buffer[1] == 1
                        and buffer[2] == nenrei and buffer[3] == 1
                        and buffer[4] == 3 and buffer[5] == seibetu):
                    _ng("新法遺族基礎年金")
                h = G.hosei_shin[IZOKU][sn]
                G.Izoku_New[KOKUNEN][sn][j][seibetu][KIHON] = buffer[6] * h
                G.Izoku_New[KOKUNEN][sn][j][seibetu][KAKYU] = buffer[7] * h

            # ---- 旧法老齢・通老年金（癖 2.） ----
            for seibetu in range(OTOKO, ONNA + 1):
                rc, _ = fp.read_data(buffer)
                if rc == -1:
                    _readerror_jisseki(4)
                if not (buffer[0] == nendo and buffer[1] == 1
                        and buffer[2] == nenrei and buffer[3] == 2
                        and buffer[4] == 1 and buffer[5] == seibetu):
                    _ng("旧法老齢・通老年金")
                h = G.hosei_kyu[KOKUNEN][sn]
                o = G.Rorei_Old[KOKUNEN][sn][j][seibetu]
                o[NOUFU] = buffer[6] * h
                o[MENJO] = buffer[7] * h
                o[KASANOUFU] = buffer[8] * h
                o[KASAMENJO] = buffer[9] * h
                o[ROFUKU_SHITASASAE] = buffer[10] * h
                o[GONEN] = buffer[11] * h

            # ---- 旧法障害年金 ----
            for seibetu in range(OTOKO, ONNA + 1):
                rc, _ = fp.read_data(buffer)
                if rc == -1:
                    _readerror_jisseki(5)
                if not (buffer[0] == nendo and buffer[1] == 1
                        and buffer[2] == nenrei and buffer[3] == 2
                        and buffer[4] == 2 and buffer[5] == seibetu):
                    _ng("旧法障害年金")
                h = G.hosei_kyu[KOKUNEN][sn]
                s = G.Shogai_Old[KOKUNEN][sn][j][seibetu]
                s[KIHON][NOUFU] = buffer[6] * h
                s[KIHON][MENJO] = buffer[7] * h
                s[KAKYU][NOUFU] = buffer[8] * h
                s[KAKYU][MENJO] = buffer[9] * h

            # ---- 旧法遺族年金 ----
            for seibetu in range(OTOKO, ONNA + 1):
                rc, _ = fp.read_data(buffer)
                if rc == -1:
                    _readerror_jisseki(6)
                if not (buffer[0] == nendo and buffer[1] == 1
                        and buffer[2] == nenrei and buffer[3] == 2
                        and buffer[4] == 3 and buffer[5] == seibetu):
                    _ng("旧法遺族年金")
                h = G.hosei_kyu[KOKUNEN][sn]
                z = G.Izoku_Old[KOKUNEN][sn][j][seibetu]
                z[KIHON][NOUFU] = buffer[6] * h
                z[KIHON][MENJO] = buffer[7] * h
                z[KAKYU][NOUFU] = buffer[8] * h
                z[KAKYU][MENJO] = buffer[9] * h

        # ---- 拠出金算定対象者数（癖 3.） ----
        rc, _ = fp.read_data(buffer)
        if rc == -1:
            _readerror_jisseki(7)
        if buffer[0] != nendo:
            _ng("拠出金算定対象者数")
        G.SanteiTaishou[KOKUNEN][sn][1] += buffer[1]
        G.SanteiTaishou[KOKUNEN][sn][1] += buffer[2]
        G.Sankyu_Taishou[sn] += buffer[3]
        G.Ikukyu_Taishou[sn] += buffer[4]

        # ---- 6行読み捨て（癖 4.・5.） ----
        for _counter in range(1, 7):
            rc, _ = fp.read_data(buffer)
            if rc == -1:
                _readerror_jisseki(8)

    # 原本は `fclose( fp_in[KOKUNEN] )`
    G.fp_in[KOKUNEN] = None
