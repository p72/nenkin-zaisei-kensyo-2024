# -*- coding: utf-8 -*-
"""
基礎年金/ReadHiyousha.c の忠実移植（②厚生年金給付費推計の出力を読む）
========================================================================
`kiso.{厚年番号}-{経済}-{外枠}_kou / _kok / _ren / _sig` の4本を読む。
`seido` は 2 厚年 / 3 国共 / 4 地共 / 5 私学で、そのまま `fp_in` の
添字にもなっている（`mfile_open.h` が 2〜5 を割り当てているため）。

`ReadKokunen_jisseki` との違い
-----------------------------
1. **年度が `西暦 - 2000`**（`buffer[0] == nendo - 2000`）。
   ③国民年金は西暦そのままなので、同じ配列に入れるのに見出しの書式が
   違う。
2. **先頭で「2019年度・2・3・2」の行まで読み飛ばす**（`while` ループ）。
   実績の部分を飛ばして推計の頭に付ける。
3. **旧法老齢の列が8つ**（`buffer[6..13]`）。加給年金（`KAKYU_NOUFU` /
   `KAKYU_MENJO`）が国年には無く被用者年金にはあるため。

原本の癖をそのまま残しているところ
----------------------------------
1. **新法遺族基礎年金のブロックだけ `else { readerror_h }` が無い**
   （`ReadHiyousha.c:332-333`）。EOF に当たると**黙って次へ進む**。
   他の5ブロックは `readerror_h( seido )` で `exit(1)` する。
   （`検証/原本の不具合.md`）

2. **読み飛ばしの `while` が EOF で止まらない判定をしていない。**
   `while( read_data( ... ) != EOF ) { if( 見出し ) break ; }` なので、
   探している行が無ければ EOF で抜けて、そのまま推計の読み込みに入る。
   そこで見出しが合わずに `exit(1)` になる。

3. **`if( sotai_nendo >= 0 )` が常に真。**`ReadKokunen_jisseki` と同じ。

4. **`counter` の6行読み捨てが空のブロック。**
"""
import sys

from cnum import Buffer
from glva import G
from setconst import (
    GONEN, HATACHIMAE, IPPAN, IZOKU, KAKYU, KAKYU_MENJO, KAKYU_NOUFU,
    KASAMENJO, KASANOUFU, KIHON, MAX_JUKYU, MENJO, MENJO_KOUHAN,
    MENJO_ZENHAN, NENREI_SUM, NOUFU, ONNA, OTOKO, ROFUKU_SHITASASAE,
    ROREI, SAISHUNENDO, SHOGAI, SHONENDO, SUIKEISHONENDO, UNDER_63,
)

__all__ = ["ReadHiyousha"]


def _readerror_h(seido):
    print("制度番号＝ %d ファイルの入力中にエラーが発生しました" % seido)
    sys.exit(1)


def _ng(where):
    print("正常に読めていません 読込箇所は%s" % where)
    sys.exit(1)


def ReadHiyousha(seido):
    """ReadHiyousha.c:235 の忠実移植。"""
    fp = G.fp_in[seido]
    buffer = Buffer()

    fp.read_headder()

    # 癖 2. 推計の頭（2019年度・2・3・2 の行）まで読み飛ばす
    while True:
        rc, _ = fp.read_data(buffer)
        if rc == -1:
            break
        if (buffer[0] == SUIKEISHONENDO - 2000 - 1 and buffer[1] == 2
                and buffer[2] == 3 and buffer[3] == 2):
            break

    for nendo in range(SUIKEISHONENDO, SAISHUNENDO + 1):
        sn = nendo - SHONENDO
        y = nendo - 2000

        for nenrei in range(UNDER_63, MAX_JUKYU + 1):
            j = nenrei - NENREI_SUM

            # ---- 新法老齢基礎年金 ----
            for seibetu in range(OTOKO, ONNA + 1):
                rc, _ = fp.read_data(buffer)
                if rc == -1:
                    _readerror_h(seido)
                if not (buffer[0] == y and buffer[1] == 1
                        and buffer[2] == nenrei and buffer[3] == 1
                        and buffer[4] == 1 and buffer[5] == seibetu):
                    _ng("新法老齢基礎年金")
                h = G.hosei_shin[ROREI][sn]
                G.Rorei_New[seido][sn][j][seibetu][NOUFU] = buffer[6] * h
                G.Rorei_New[seido][sn][j][seibetu][MENJO_ZENHAN] = \
                    buffer[7] * h
                G.Rorei_New[seido][sn][j][seibetu][MENJO_KOUHAN] = \
                    buffer[8] * h
                G.FurikaeKasan[seido][sn][j][seibetu][ROREI] = buffer[9] * h

            # ---- 新法障害基礎年金 ----
            for seibetu in range(OTOKO, ONNA + 1):
                rc, _ = fp.read_data(buffer)
                if rc == -1:
                    _readerror_h(seido)
                if not (buffer[0] == y and buffer[1] == 1
                        and buffer[2] == nenrei and buffer[3] == 1
                        and buffer[4] == 2 and buffer[5] == seibetu):
                    _ng("新法障害基礎年金")
                h = G.hosei_shin[SHOGAI][sn]
                G.Shogai_New[seido][sn][j][seibetu][IPPAN][KIHON] = \
                    buffer[6] * h
                G.Shogai_New[seido][sn][j][seibetu][IPPAN][KAKYU] = \
                    buffer[7] * h
                G.FurikaeKasan[seido][sn][j][seibetu][SHOGAI] = buffer[8] * h
                G.Shogai_New[seido][sn][j][seibetu][HATACHIMAE][KIHON] = \
                    buffer[9] * h
                G.Shogai_New[seido][sn][j][seibetu][HATACHIMAE][KAKYU] = \
                    buffer[10] * h

            # ---- 新法遺族基礎年金（癖 1. EOF でも止まらない） ----
            for seibetu in range(OTOKO, ONNA + 1):
                rc, _ = fp.read_data(buffer)
                if rc == -1:
                    continue
                if not (buffer[0] == y and buffer[1] == 1
                        and buffer[2] == nenrei and buffer[3] == 1
                        and buffer[4] == 3 and buffer[5] == seibetu):
                    _ng("新法遺族基礎年金")
                h = G.hosei_shin[IZOKU][sn]
                G.Izoku_New[seido][sn][j][seibetu][KIHON] = buffer[6] * h
                G.Izoku_New[seido][sn][j][seibetu][KAKYU] = buffer[7] * h

            # ---- 旧法老齢・通老年金（列が8つ） ----
            for seibetu in range(OTOKO, ONNA + 1):
                rc, _ = fp.read_data(buffer)
                if rc == -1:
                    _readerror_h(seido)
                if not (buffer[0] == y and buffer[1] == 1
                        and buffer[2] == nenrei and buffer[3] == 2
                        and buffer[4] == 1 and buffer[5] == seibetu):
                    _ng("旧法老齢・通老年金")
                h = G.hosei_kyu[seido][sn]
                o = G.Rorei_Old[seido][sn][j][seibetu]
                o[NOUFU] = buffer[6] * h
                o[MENJO] = buffer[7] * h
                o[KAKYU_NOUFU] = buffer[8] * h
                o[KAKYU_MENJO] = buffer[9] * h
                o[KASANOUFU] = buffer[10] * h
                o[KASAMENJO] = buffer[11] * h
                o[ROFUKU_SHITASASAE] = buffer[12] * h
                o[GONEN] = buffer[13] * h

            # ---- 旧法障害年金 ----
            for seibetu in range(OTOKO, ONNA + 1):
                rc, _ = fp.read_data(buffer)
                if rc == -1:
                    _readerror_h(seido)
                if not (buffer[0] == y and buffer[1] == 1
                        and buffer[2] == nenrei and buffer[3] == 2
                        and buffer[4] == 2 and buffer[5] == seibetu):
                    _ng("旧法障害年金")
                h = G.hosei_kyu[seido][sn]
                s = G.Shogai_Old[seido][sn][j][seibetu]
                s[KIHON][NOUFU] = buffer[6] * h
                s[KIHON][MENJO] = buffer[7] * h
                s[KAKYU][NOUFU] = buffer[8] * h
                s[KAKYU][MENJO] = buffer[9] * h

            # ---- 旧法遺族年金 ----
            for seibetu in range(OTOKO, ONNA + 1):
                rc, _ = fp.read_data(buffer)
                if rc == -1:
                    _readerror_h(seido)
                if not (buffer[0] == y and buffer[1] == 1
                        and buffer[2] == nenrei and buffer[3] == 2
                        and buffer[4] == 3 and buffer[5] == seibetu):
                    _ng("旧法遺族年金")
                h = G.hosei_kyu[seido][sn]
                z = G.Izoku_Old[seido][sn][j][seibetu]
                z[KIHON][NOUFU] = buffer[6] * h
                z[KIHON][MENJO] = buffer[7] * h
                z[KAKYU][NOUFU] = buffer[8] * h
                z[KAKYU][MENJO] = buffer[9] * h

        # ---- 6行読み捨て（癖 4.） ----
        for _counter in range(1, 7):
            rc, _ = fp.read_data(buffer)
            if rc == -1:
                _readerror_h(seido)

    # 原本は `fclose( fp_in[seido] )`
    G.fp_in[seido] = None
