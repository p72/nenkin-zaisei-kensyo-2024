# -*- coding: utf-8 -*-
"""
国民年金/dtst.c の忠実移植（足元の基礎数を13本のファイルから読む）
===================================================================
856 行。`main.c` が種別（2 第1号男 / 3 第3号男 / 5 第1号女 /
6 第3号女）ごとに1回呼ぶ。2021年度（`SUIKEISHONENDO`）の
実績を読んで、`*_Nendomatu` の足元の年度に入れる。

    Hihokensha / Taikisha                 被保険者・待期者
    Rorei_Nendomatu / Rorei_Ichibu_…      老齢基礎（一部繰上げを分けて）
    Rorei_Kyu_Nendomatu / Turo_Kyu_…      旧法の老齢・通算老齢
    Gonen_Nendomatu                       5年年金
    Shogai_Ippan / _20mae / _Kyu_…        障害基礎（一般・20歳前・旧法）
    Izoku_Tuma / _Otto / _Ko_…            遺族基礎（妻・夫・子）
    Kafu_Nendomatu / Kafu_Kyu_…           寡婦年金（新法・旧法）
    Ichijikin_Nendomatu                   死亡一時金（**0 にするだけ**）

種別で読むファイルの本数が違う
------------------------------
```c
switch( shubetu ) {
  case 2 : for( counter = 0 ; counter < 13 ; counter++ ) fp[counter] = fp_in[DTST_1M + counter]; break;
  case 3 : for( counter = 0 ; counter <  4 ; counter++ ) fp[counter] = fp_in[DTST_3M + counter]; break;
  case 5 : for( counter = 0 ; counter < 11 ; counter++ ) fp[counter] = fp_in[DTST_1F + counter]; break;
  case 6 : for( counter = 0 ; counter <  4 ; counter++ ) fp[counter] = fp_in[DTST_3F + counter]; break;
}
```

| 種別 | 本数 | 中身 |
|---|---:|---|
| 2 第1号男 | 13 | 全部（寡婦・遺族子は男だけが持つ） |
| 3 第3号男 | 4 | 被保険者・待期者・老齢基礎2本 |
| 5 第1号女 | 11 | 寡婦・遺族子を除く |
| 6 第3号女 | 4 | 3 と同じ |

`fp[…]` の中身（`fp` は13要素の局所配列）

    0,1   被保険者・待期者
    2,3   老齢基礎・老齢基礎（一部繰上げ）
    4,5   旧法老齢・旧法通算老齢
    6     5年年金
    7,8,9 障害（一般・20歳前・旧法）
    10    遺族（妻 or 夫）
    11    遺族（子）
    12    寡婦

**種別 3・6 は `fp[4]` 以降を入れない**ので、`fp[4..12]` は
**未初期化のポインタ**。`if( shubetu == 2 || shubetu == 5 )` で
守られているので読まれない。

`double buffer[53]` は紙一重
----------------------------
被保険者の行は `buffer[counter + 3]` を `counter` = 0〜49 で読むので
**添字 52 まで**使う。`buffer[53]` にちょうど収まる。
列が1つ増えると配列の外に書き込む（`検証/原本の不具合.md` C の仲間）。

70歳と50年目は読まない
----------------------
```c
for( nenrei = MIN_HIHO_NENREI ; nenrei <= MAX_HIHO_NENREI - 1 ; nenrei++ )
  …
  for( counter = 0 ; counter <= MAX_HIHO_KIKAN - 1 ; counter++ )
```

年齢は 20〜**69**（`MAX_HIHO_NENREI - 1`）、加入期間は 0〜**49**
（`MAX_HIHO_KIKAN - 1`）。配列は 70歳・50年目まであるが
**足元の実績には入れない**（0 のまま）。70歳の第1号被保険者と
50年加入は制度上あり得ないので意図どおり。

寡婦は 65〜69歳を読んで捨てる
-----------------------------
```c
for( nenrei = MIN_KAFU_JUKYU ; nenrei <= 69 ; nenrei++ ) {
  if( read_data( … ) != EOF ) {
    if( buffer[0] != 13 ) { … exit( 1 ); }
    else { if( nenrei <= 64 ) { … 入れる … } }
  }
}
```

ファイルには 26〜69歳の44行あるが、入れるのは **64歳まで**
（`MAX_KAFU_JUKYU` = 64。寡婦年金は65歳で老齢基礎に切り替わる）。
65〜69歳の5行は**読んで形だけ確かめて捨てる**。

障害は等級 1 と 2 だけ入る
--------------------------
```c
for( counter = 0 ; counter <= 9 ; counter++ ) {
  switch( counter % 5 ) {
    case 0 : S_temp[…][counter / 5 + 1].ninzu = buffer[counter + 2]; break;
    …
  }
}
```

`counter / 5 + 1` なので `counter` 0〜4 が**等級 1**、5〜9 が
**等級 2**。`S_temp[…][0]`（`SHOGAI_TOKYU` の添字 0）は
**入らない**（0 のまま）。3級は基礎年金に無いので 2 段階で正しく、
添字 0 は「計」の欄。

5年年金は受給開始年齢を 65 に固定する
------------------------------------
```c
Gonen_Nendomatu[…][nenrei - MIN_ROREI_JUKYU][65 - MIN_ROREI_JUKYU].ninzu = buffer[2];
Gonen_Nendomatu[…][nenrei - MIN_ROREI_JUKYU][65 - MIN_ROREI_JUKYU].noufu = buffer[3];
```

3つ目の添字（繰上げ・繰下げの区分）は **`65 - 60` = 5 固定**。
5年年金（旧法の特例）は繰上げ・繰下げが無い。

`Ichijikin_Nendomatu` だけ全年度を 0 にする
------------------------------------------
ほかは `SUIKEISHONENDO` の年度だけ 0 にするが、死亡一時金は

```c
for( nendo = SHONENDO ; nendo <= SAISHUNENDO ; nendo++ )
  for( nenrei = … ) Ichijikin_Nendomatu[nendo - SHONENDO][…] = Ichijikin_Zero;
```

と **2020〜2125年度の全部**を 0 にする。`dtst()` は種別4通りで
呼ばれるので4回 0 にし直す。足元の実績が無い（死亡一時金は
推計で作る）ため。

第3号は老齢基礎の納付月数だけ読む
--------------------------------
```c
else if( shubetu == 3 || shubetu == 6 ) {
  read_data( buffer , fp[counter2 + 2] , &data_number );
  for( nenrei = … ) {
    if( … && buffer[1] != 2 ) { … exit( 1 ); }
    else for( counter = 0 ; counter <= 10 ; counter++ )
      R_temp[counter2][…][counter].noufu = buffer[counter + 3];
  }
}
```

第3号の老齢基礎のファイルは **`member` が 2（納付月数）の行だけ**。
人数も免除も無い（第3号は保険料を納めないので全期間が納付扱い）。

エラーの「基礎数種類」の番号が `fp` の添字と合っていない
-------------------------------------------------------
```c
read_data( buffer , fp[counter2 + 2] , … );      /* fp[2] か fp[3] */
…
readkisosu_error( counter2 + 3 );                /* 3 か 4 と出る */
```

`fp` の添字は 0 起点、エラーの番号は 1 起点で数えているが、
`fp[counter2+4]`（旧法）のときは `readkisosu_error( counter2 + 4 )`
と**ずれ方が違う**（4 か 5 と出るので旧法通算老齢のときも 5）。
落ちたときの表示だけの話。
"""
import numpy as np

from setconst import (MAX_HIHO_KIKAN, MAX_HIHO_NENREI, MAX_IZOKU_KO_JUKYU,
                      MAX_IZOKU_OTTO_JUKYU, MAX_IZOKU_TUMA_JUKYU,
                      MAX_KAFU_JUKYU, MAX_ROREI_JUKYU, MAX_SHOGAI_JUKYU,
                      MENJO_1_2, MENJO_1_4, MENJO_3_4, MIN_HIHO_NENREI,
                      MIN_IZOKU_KO_JUKYU, MIN_IZOKU_OTTO_JUKYU,
                      MIN_IZOKU_TUMA_JUKYU, MIN_KAFU_JUKYU,
                      MIN_ROREI_JUKYU, MIN_SHOGAI_JUKYU, SAISHUNENDO,
                      SHOGAI_TOKYU, SHONENDO, SUIKEISHONENDO, ZENGAKU)
from stdfm import EOF, Buffer, NatError, read_data

__all__ = ["dtst"]

# `mfile_open.h` の入力番号
_DTST_1M = 17
_DTST_3M = 30
_DTST_1F = 34
_DTST_3F = 45

_KIJUN = SUIKEISHONENDO - SHONENDO       # 足元の年度の添字（= 1）


def readkisosu_error(shurui):
    """dtst.c:852 の忠実移植。"""
    raise NatError(
        "基礎数ファイル読み込み中にＥＯＦを検出しました。 基礎数種類は、%d"
        % shurui)


# 被保険者・待期者の `member` → 入れる欄（dtst.c:104-176）
#   欄名か ("menjo", 段階, 期間) のどちらか
_H_MEMBER = {
    1: "ninzu",
    2: "kikan",
    3: "noufu",
    4: ("menjo", ZENGAKU, 1),
    5: ("menjo", MENJO_3_4, 1),
    6: ("menjo", MENJO_1_2, 1),
    7: ("menjo", MENJO_1_4, 1),
    8: "gakusei",
    9: "wakamono",
    10: "fuka",
    11: ("menjo", ZENGAKU, 2),
    12: ("menjo", MENJO_3_4, 2),
    13: ("menjo", MENJO_1_2, 2),
    14: ("menjo", MENJO_1_4, 2),
}

# 老齢基礎の `member` → 入れる欄（dtst.c:240-306）
_R_MEMBER = {
    1: "ninzu",
    2: "noufu",
    3: ("menjo", ZENGAKU, 1),
    4: ("menjo", MENJO_3_4, 1),
    5: ("menjo", MENJO_1_2, 1),
    6: ("menjo", MENJO_1_4, 1),
    7: "rofuku_shitasasae",
    8: "fuka",
    9: ("menjo", ZENGAKU, 2),
    10: ("menjo", MENJO_3_4, 2),
    11: ("menjo", MENJO_1_2, 2),
    12: ("menjo", MENJO_1_4, 2),
}

# 旧法老齢・旧法通算老齢の `member` → 入れる欄（dtst.c:388-424）
_K_MEMBER = {
    1: "ninzu",
    2: "noufu",
    3: "menjo",
    4: "kasa_noufu",
    5: "kasa_menjo",
    6: "rofuku_shitasasae",
    7: "fuka",
}

# 障害の `counter % 5` → 入れる欄（dtst.c:520-546）
_S_FIELD = ("ninzu", "kihon", "kakyu", "menjo_kihon", "menjo_kakyu")

# 遺族（妻・夫・子）の `counter` → 入れる欄
_I_FIELD = ("ninzu", "kihon", "kakyu")

# 寡婦の `counter` → (どちらの配列か, 入れる欄)（dtst.c:744-822）
#   "kyu" は `Kafu_Kyu_Nendomatu`、"new" は `Kafu_Nendomatu`
_KAFU_FIELD = {
    0: ("kyu", "ninzu"),
    1: ("kyu", "noufu"),
    2: ("kyu", ("menjo", ZENGAKU, 1)),
    3: ("new", "ninzu"),
    4: ("new", "noufu"),
    5: ("new", ("menjo", ZENGAKU, 1)),
    6: ("new", ("menjo", MENJO_3_4, 1)),
    7: ("new", ("menjo", MENJO_1_2, 1)),
    8: ("new", ("menjo", MENJO_1_4, 1)),
    9: ("kyu", ("menjo", ZENGAKU, 2)),
    10: ("new", ("menjo", ZENGAKU, 2)),
    11: ("new", ("menjo", MENJO_3_4, 2)),
    12: ("new", ("menjo", MENJO_1_2, 2)),
    13: ("new", ("menjo", MENJO_1_4, 2)),
}


def _put(rec, spec, v):
    """`rec`（構造体1個のビュー）の `spec` が指す欄に `v` を入れる。"""
    if isinstance(spec, tuple):
        rec["menjo"][spec[1], spec[2]] = v
    else:
        rec[spec] = v


def dtst(G, shubetu):
    """dtst.c:15 の忠実移植。"""
    buf = Buffer(53)            # 原本は `double buffer[53]`（紙一重）

    # 原本は `FILE *fp[13]`。種別 3・6 では 4本だけ入れて残りは未初期化
    fp = [None] * 13
    if shubetu == 2:
        for counter in range(0, 13):
            fp[counter] = G.fp_in[_DTST_1M + counter]
    elif shubetu == 3:
        for counter in range(0, 4):
            fp[counter] = G.fp_in[_DTST_3M + counter]
    elif shubetu == 5:
        for counter in range(0, 11):
            fp[counter] = G.fp_in[_DTST_1F + counter]
    elif shubetu == 6:
        for counter in range(0, 4):
            fp[counter] = G.fp_in[_DTST_3F + counter]
    else:
        raise NatError("指定外のshubetu %d を読み込みました" % shubetu)

    if shubetu == 2 or shubetu == 5:
        kubun = 14
    else:
        kubun = 3

    # ---- 被保険者・待期者 ------------------------------------------
    H_temp = np.zeros((2, MAX_HIHO_NENREI - MIN_HIHO_NENREI + 1,
                       MAX_HIHO_KIKAN + 1), dtype=G.Hihokensha.dtype)

    for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
        for kikan in range(0, MAX_HIHO_KIKAN + 1):
            H_temp[0, nenrei - MIN_HIHO_NENREI, kikan] = G.Hihokensha_Zero
            H_temp[1, nenrei - MIN_HIHO_NENREI, kikan] = G.Taikisha_Zero
            G.Hihokensha[_KIJUN, nenrei - MIN_HIHO_NENREI, kikan] = \
                G.Hihokensha_Zero
            G.Taikisha[_KIJUN, nenrei - MIN_HIHO_NENREI, kikan] = \
                G.Taikisha_Zero

    for counter2 in range(0, 1 + 1):
        read_data(buf, fp[counter2])        # 見出しを1行

        for member in range(1, kubun + 1):
            # **69歳まで**（70歳は読まない）
            for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI - 1 + 1):
                if read_data(buf, fp[counter2]) != EOF:
                    if (buf.num[0] != counter2 + 1
                            or buf.num[1] != member):
                        raise NatError(
                            "被保険者あるいは待期者の読込が正常に行われて"
                            "いません %s %s %d %d"
                            % (buf.num[0], buf.num[1], member, nenrei))
                    else:
                        spec = _H_MEMBER[member]
                        # **49年目まで**（50年目は読まない）
                        for counter in range(0, MAX_HIHO_KIKAN - 1 + 1):
                            v = buf.num[counter + 3]
                            if member != 1:
                                # 人数以外は月数なので 12 で割る
                                v = v / 12.
                            _put(H_temp[counter2,
                                        nenrei - MIN_HIHO_NENREI, counter],
                                 spec, v)
                else:
                    readkisosu_error(counter2 + 1)

    for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
        for kikan in range(0, MAX_HIHO_KIKAN + 1):
            G.Hihokensha[_KIJUN, nenrei - MIN_HIHO_NENREI, kikan] = \
                H_temp[0, nenrei - MIN_HIHO_NENREI, kikan]
            G.Taikisha[_KIJUN, nenrei - MIN_HIHO_NENREI, kikan] = \
                H_temp[1, nenrei - MIN_HIHO_NENREI, kikan]

    # ---- 老齢基礎（本体と一部繰上げ）-------------------------------
    _N_ROREI = MAX_ROREI_JUKYU - MIN_ROREI_JUKYU + 1
    _N_KAS = 70 - MIN_ROREI_JUKYU + 1           # 11
    R_temp = np.zeros((2, _N_ROREI, _N_KAS), dtype=G.Rorei.dtype)

    for nenrei in range(MIN_ROREI_JUKYU, MAX_ROREI_JUKYU + 1):
        for jukyu_nenrei in range(MIN_ROREI_JUKYU, 70 + 1):
            R_temp[0, nenrei - MIN_ROREI_JUKYU,
                   jukyu_nenrei - MIN_ROREI_JUKYU] = G.Rorei_Zero
            R_temp[1, nenrei - MIN_ROREI_JUKYU,
                   jukyu_nenrei - MIN_ROREI_JUKYU] = G.Rorei_Zero
            G.Rorei_Nendomatu[_KIJUN, nenrei - MIN_ROREI_JUKYU,
                              jukyu_nenrei - MIN_ROREI_JUKYU] = G.Rorei_Zero
            G.Rorei_Ichibu_Nendomatu[
                _KIJUN, nenrei - MIN_ROREI_JUKYU,
                jukyu_nenrei - MIN_ROREI_JUKYU] = G.Rorei_Zero

    for counter2 in range(0, 1 + 1):
        if shubetu == 2 or shubetu == 5:
            read_data(buf, fp[counter2 + 2])

            for member in range(1, 12 + 1):
                for nenrei in range(MIN_ROREI_JUKYU, MAX_ROREI_JUKYU + 1):
                    if read_data(buf, fp[counter2 + 2]) != EOF:
                        if (buf.num[0] != counter2 + 3
                                or buf.num[1] != member):
                            raise NatError(
                                "老齢基礎年金または老齢基礎年金（一部繰り"
                                "上げ者）の読込が正常に行われていません "
                                "%s %s %d %s"
                                % (buf.num[0], buf.num[1], member,
                                   buf.num[3]))
                        else:
                            spec = _R_MEMBER[member]
                            for counter in range(0, 10 + 1):
                                _put(R_temp[counter2,
                                            nenrei - MIN_ROREI_JUKYU,
                                            counter],
                                     spec, buf.num[counter + 3])
                    else:
                        readkisosu_error(counter2 + 3)
        elif shubetu == 3 or shubetu == 6:
            # 第3号は納付月数（`member` = 2）の行だけ
            read_data(buf, fp[counter2 + 2])

            for nenrei in range(MIN_ROREI_JUKYU, MAX_ROREI_JUKYU + 1):
                if read_data(buf, fp[counter2 + 2]) != EOF:
                    if buf.num[0] != counter2 + 3 or buf.num[1] != 2:
                        raise NatError(
                            "老齢基礎年金または老齢基礎年金（一部繰り"
                            "上げ者）の読込が正常に行われていません "
                            "%s %s %d %s"
                            % (buf.num[0], buf.num[1], 2, buf.num[3]))
                    else:
                        for counter in range(0, 10 + 1):
                            R_temp[counter2, nenrei - MIN_ROREI_JUKYU,
                                   counter]["noufu"] = buf.num[counter + 3]
                else:
                    readkisosu_error(counter2 + 3)

    for nenrei in range(MIN_ROREI_JUKYU, MAX_ROREI_JUKYU + 1):
        for jukyu_nenrei in range(MIN_ROREI_JUKYU, 70 + 1):
            G.Rorei_Nendomatu[_KIJUN, nenrei - MIN_ROREI_JUKYU,
                              jukyu_nenrei - MIN_ROREI_JUKYU] = \
                R_temp[0, nenrei - MIN_ROREI_JUKYU,
                       jukyu_nenrei - MIN_ROREI_JUKYU]

            G.Rorei_Ichibu_Nendomatu[_KIJUN, nenrei - MIN_ROREI_JUKYU,
                                     jukyu_nenrei - MIN_ROREI_JUKYU] = \
                R_temp[1, nenrei - MIN_ROREI_JUKYU,
                       jukyu_nenrei - MIN_ROREI_JUKYU]

    # ---- 旧法の老齢・通算老齢 --------------------------------------
    K_temp = np.zeros((2, _N_ROREI, _N_KAS), dtype=G.Rorei_Kyu.dtype)

    for nenrei in range(MIN_ROREI_JUKYU, MAX_ROREI_JUKYU + 1):
        for jukyu_nenrei in range(MIN_ROREI_JUKYU, 70 + 1):
            K_temp[0, nenrei - MIN_ROREI_JUKYU,
                   jukyu_nenrei - MIN_ROREI_JUKYU] = G.Rorei_Kyu_Zero
            K_temp[1, nenrei - MIN_ROREI_JUKYU,
                   jukyu_nenrei - MIN_ROREI_JUKYU] = G.Rorei_Kyu_Zero
            G.Rorei_Kyu_Nendomatu[_KIJUN, nenrei - MIN_ROREI_JUKYU,
                                  jukyu_nenrei - MIN_ROREI_JUKYU] = \
                G.Rorei_Kyu_Zero
            G.Turo_Kyu_Nendomatu[_KIJUN, nenrei - MIN_ROREI_JUKYU,
                                 jukyu_nenrei - MIN_ROREI_JUKYU] = \
                G.Rorei_Kyu_Zero

    for counter2 in range(0, 1 + 1):
        if shubetu == 2 or shubetu == 5:
            read_data(buf, fp[counter2 + 4])

            for member in range(1, 7 + 1):
                for nenrei in range(MIN_ROREI_JUKYU, MAX_ROREI_JUKYU + 1):
                    if read_data(buf, fp[counter2 + 4]) != EOF:
                        if (buf.num[0] != counter2 + 5
                                or buf.num[1] != member):
                            raise NatError(
                                "旧法老齢あるいは通算老齢の読込が正常に"
                                "行われていません %s %s %d"
                                % (buf.num[0], buf.num[1], member))
                        else:
                            spec = _K_MEMBER[member]
                            for counter in range(0, 10 + 1):
                                _put(K_temp[counter2,
                                            nenrei - MIN_ROREI_JUKYU,
                                            counter],
                                     spec, buf.num[counter + 3])
                    else:
                        readkisosu_error(counter2 + 4)

    for nenrei in range(MIN_ROREI_JUKYU, MAX_ROREI_JUKYU + 1):
        for jukyu_nenrei in range(MIN_ROREI_JUKYU, 70 + 1):
            G.Rorei_Kyu_Nendomatu[_KIJUN, nenrei - MIN_ROREI_JUKYU,
                                  jukyu_nenrei - MIN_ROREI_JUKYU] = \
                K_temp[0, nenrei - MIN_ROREI_JUKYU,
                       jukyu_nenrei - MIN_ROREI_JUKYU]

            G.Turo_Kyu_Nendomatu[_KIJUN, nenrei - MIN_ROREI_JUKYU,
                                 jukyu_nenrei - MIN_ROREI_JUKYU] = \
                K_temp[1, nenrei - MIN_ROREI_JUKYU,
                       jukyu_nenrei - MIN_ROREI_JUKYU]

    # ---- 5年年金 ---------------------------------------------------
    for nenrei in range(MIN_ROREI_JUKYU, MAX_ROREI_JUKYU + 1):
        for jukyu_nenrei in range(MIN_ROREI_JUKYU, 70 + 1):
            G.Gonen_Nendomatu[_KIJUN, nenrei - MIN_ROREI_JUKYU,
                              jukyu_nenrei - MIN_ROREI_JUKYU] = G.Gonen_Zero

    if shubetu == 2 or shubetu == 5:
        read_data(buf, fp[6])

        for nenrei in range(MIN_ROREI_JUKYU, MAX_ROREI_JUKYU + 1):
            if read_data(buf, fp[6]) != EOF:
                if buf.num[0] != 7:
                    raise NatError(
                        "５年年金の読込が正常に行われていません %s"
                        % buf.num[0])
                else:
                    # 受給開始年齢の添字は **65 固定**
                    G.Gonen_Nendomatu[_KIJUN, nenrei - MIN_ROREI_JUKYU,
                                      65 - MIN_ROREI_JUKYU]["ninzu"] = \
                        buf.num[2]
                    G.Gonen_Nendomatu[_KIJUN, nenrei - MIN_ROREI_JUKYU,
                                      65 - MIN_ROREI_JUKYU]["noufu"] = \
                        buf.num[3]
            else:
                readkisosu_error(6)

    # ---- 障害基礎（一般・20歳前・旧法）----------------------------
    _N_SHOGAI = MAX_SHOGAI_JUKYU - MIN_SHOGAI_JUKYU + 1
    S_temp = np.zeros((3, _N_SHOGAI, SHOGAI_TOKYU),
                      dtype=G.Shogai_Ippan.dtype)

    for nenrei in range(MIN_SHOGAI_JUKYU, MAX_SHOGAI_JUKYU + 1):
        for tokyu in range(0, 2 + 1):
            S_temp[0, nenrei - MIN_SHOGAI_JUKYU, tokyu] = G.Shogai_Zero
            S_temp[1, nenrei - MIN_SHOGAI_JUKYU, tokyu] = G.Shogai_Zero
            S_temp[2, nenrei - MIN_SHOGAI_JUKYU, tokyu] = G.Shogai_Zero
            G.Shogai_Ippan_Nendomatu[_KIJUN, nenrei - MIN_SHOGAI_JUKYU,
                                     tokyu] = G.Shogai_Zero
            G.Shogai_20mae_Nendomatu[_KIJUN, nenrei - MIN_SHOGAI_JUKYU,
                                     tokyu] = G.Shogai_Zero
            G.Shogai_Kyu_Nendomatu[_KIJUN, nenrei - MIN_SHOGAI_JUKYU,
                                   tokyu] = G.Shogai_Zero

    for counter2 in range(0, 2 + 1):
        if shubetu == 2 or shubetu == 5:
            read_data(buf, fp[counter2 + 7])

            for nenrei in range(MIN_SHOGAI_JUKYU, MAX_SHOGAI_JUKYU + 1):
                if read_data(buf, fp[counter2 + 7]) != EOF:
                    if buf.num[0] != counter2 + 8:
                        raise NatError(
                            "障害基礎（一般）、障害基礎（２０歳前）または"
                            "旧法障害の読込が正常に行われていません %s"
                            % buf.num[0])
                    else:
                        # `counter / 5 + 1` なので等級 1 と 2 だけ入る
                        for counter in range(0, 9 + 1):
                            S_temp[counter2, nenrei - MIN_SHOGAI_JUKYU,
                                   counter // 5 + 1][
                                       _S_FIELD[counter % 5]] = \
                                buf.num[counter + 2]
                else:
                    readkisosu_error(counter2 + 7)

    for nenrei in range(MIN_SHOGAI_JUKYU, MAX_SHOGAI_JUKYU + 1):
        for tokyu in range(0, 2 + 1):
            G.Shogai_Ippan_Nendomatu[_KIJUN, nenrei - MIN_SHOGAI_JUKYU,
                                     tokyu] = \
                S_temp[0, nenrei - MIN_SHOGAI_JUKYU, tokyu]
            G.Shogai_20mae_Nendomatu[_KIJUN, nenrei - MIN_SHOGAI_JUKYU,
                                     tokyu] = \
                S_temp[1, nenrei - MIN_SHOGAI_JUKYU, tokyu]
            G.Shogai_Kyu_Nendomatu[_KIJUN, nenrei - MIN_SHOGAI_JUKYU,
                                   tokyu] = \
                S_temp[2, nenrei - MIN_SHOGAI_JUKYU, tokyu]

    # ---- 遺族基礎（妻・夫）----------------------------------------
    for nenrei in range(MIN_IZOKU_TUMA_JUKYU, MAX_IZOKU_TUMA_JUKYU + 1):
        G.Izoku_Tuma_Nendomatu[_KIJUN,
                               nenrei - MIN_IZOKU_TUMA_JUKYU] = G.Izoku_Zero

    for nenrei in range(MIN_IZOKU_OTTO_JUKYU, MAX_IZOKU_OTTO_JUKYU + 1):
        G.Izoku_Otto_Nendomatu[_KIJUN,
                               nenrei - MIN_IZOKU_OTTO_JUKYU] = G.Izoku_Zero

    if shubetu == 2:
        # 第1号男のファイルには「妻」が入っている
        read_data(buf, fp[10])

        for nenrei in range(MIN_IZOKU_TUMA_JUKYU,
                            MAX_IZOKU_TUMA_JUKYU + 1):
            if read_data(buf, fp[10]) != EOF:
                if buf.num[0] != 11:
                    raise NatError(
                        "遺族（妻）の読込が正常に行われていません %s"
                        % buf.num[0])
                else:
                    for counter in range(0, 2 + 1):
                        G.Izoku_Tuma_Nendomatu[
                            _KIJUN, nenrei - MIN_IZOKU_TUMA_JUKYU][
                                _I_FIELD[counter]] = buf.num[counter + 2]
            else:
                readkisosu_error(10)

    if shubetu == 5:
        # 第1号女のファイルには「夫」が入っている
        read_data(buf, fp[10])

        for nenrei in range(MIN_IZOKU_OTTO_JUKYU,
                            MAX_IZOKU_OTTO_JUKYU + 1):
            if read_data(buf, fp[10]) != EOF:
                if buf.num[0] != 11:
                    raise NatError(
                        "遺族（夫）の読込が正常に行われていません %s"
                        % buf.num[0])
                else:
                    for counter in range(0, 2 + 1):
                        G.Izoku_Otto_Nendomatu[
                            _KIJUN, nenrei - MIN_IZOKU_OTTO_JUKYU][
                                _I_FIELD[counter]] = buf.num[counter + 2]
            else:
                readkisosu_error(10)

    # ---- 遺族基礎（子）--------------------------------------------
    for nenrei in range(MIN_IZOKU_KO_JUKYU, MAX_IZOKU_KO_JUKYU + 1):
        G.Izoku_Ko_Nendomatu[_KIJUN,
                             nenrei - MIN_IZOKU_KO_JUKYU] = G.Izoku_Zero

    if shubetu == 2:
        read_data(buf, fp[11])

        for nenrei in range(MIN_IZOKU_KO_JUKYU, MAX_IZOKU_KO_JUKYU + 1):
            if read_data(buf, fp[11]) != EOF:
                if buf.num[0] != 12:
                    raise NatError(
                        "遺族（子）の読込が正常に行われていません %s"
                        % buf.num[0])
                else:
                    for counter in range(0, 2 + 1):
                        G.Izoku_Ko_Nendomatu[
                            _KIJUN, nenrei - MIN_IZOKU_KO_JUKYU][
                                _I_FIELD[counter]] = buf.num[counter + 2]
            else:
                readkisosu_error(11)

    # ---- 寡婦年金（新法・旧法）------------------------------------
    for nenrei in range(MIN_KAFU_JUKYU, MAX_KAFU_JUKYU + 1):
        G.Kafu_Nendomatu[_KIJUN, nenrei - MIN_KAFU_JUKYU] = G.Kafu_Zero
        G.Kafu_Kyu_Nendomatu[_KIJUN, nenrei - MIN_KAFU_JUKYU] = G.Kafu_Zero

    if shubetu == 2:
        read_data(buf, fp[12])

        # **69歳まで読んで、入れるのは64歳まで**
        for nenrei in range(MIN_KAFU_JUKYU, 69 + 1):
            if read_data(buf, fp[12]) != EOF:
                if buf.num[0] != 13:
                    raise NatError(
                        "寡婦年金の読込が正常に行われていません%s"
                        % buf.num[0])
                else:
                    if nenrei <= 64:
                        for counter in range(0, 13 + 1):
                            which, spec = _KAFU_FIELD[counter]
                            if which == "kyu":
                                rec = G.Kafu_Kyu_Nendomatu[
                                    _KIJUN, nenrei - MIN_KAFU_JUKYU]
                            else:
                                rec = G.Kafu_Nendomatu[
                                    _KIJUN, nenrei - MIN_KAFU_JUKYU]
                            _put(rec, spec, buf.num[counter + 2])
            else:
                readkisosu_error(12)

    # ---- 死亡一時金（全年度を 0 にするだけ）-----------------------
    for nendo in range(SHONENDO, SAISHUNENDO + 1):
        for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
            G.Ichijikin_Nendomatu[nendo - SHONENDO,
                                  nenrei - MIN_HIHO_NENREI] = \
                G.Ichijikin_Zero
