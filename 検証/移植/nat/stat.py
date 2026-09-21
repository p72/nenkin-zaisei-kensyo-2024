# -*- coding: utf-8 -*-
"""
国民年金/stat.c の忠実移植（集計と2本の出力）
=============================================
**このモジュールは `import stat` では読めない。** Python の標準
ライブラリに同じ名前があり、`os` が起動時に読み込むので
`sys.modules["stat"]` は必ず埋まっている（消すと `pathlib` や
`tarfile` が壊れる）。②の `emp_kyufu/stat.py` と同じで、

```python
import importlib.util as ilu
spec = ilu.spec_from_file_location("nat_stat", "nat/stat.py")
mod = ilu.module_from_spec(spec)
sys.modules["nat_stat"] = mod
spec.loader.exec_module(mod)
```

で読む。`nat/natload.py` の `load_stat()` がこれをやる。

747 行。`main.c` が種別ループを抜けたあと**1回だけ**呼ぶ。
`shke()` が種別・年齢階級ごとに積んだものを

1. 被保険者・納付・免除の**年度間平均**（前年度の「翌年度の率で
   見たぶん」と当年度の平均）に直す
2. 受給資格別・男女別・全体の**計**を作る（`Hanbetu()` で男女に
   振り分け、`SHUBETU_SUM` に全部を足す）
3. **年度間受給者数**（`*_Jukyu_Nendokan`）を出す
4. 2本のファイルを書く

    KISONENKIN  ④基礎年金が読む（基礎年金拠出金の計算に使う）
    DOKUZI      独自給付（付加年金・寡婦年金・死亡一時金・国庫負担）

種別の添字の使い分け
--------------------
`Rorei[shubetu][…]` などの1番目の添字は 10 まである。

    0            `SHUBETU_SUM`  全部の計
    2 3 5 6      種別（第1号男・第3号男・第1号女・第3号女）
    7            `SHUBETU_OTOKO` 男の計（`Hanbetu()` が 2・3 を集める）
    8            `SHUBETU_ONNA`  女の計（同 5・6）

`Hanbetu( shubetu )` は `shubetu <= 3 ? SHUBETU_OTOKO : SHUBETU_ONNA`。

出力の `shubetu - 6` は 7 → **1**、8 → **2** になる（男 1・女 2）。

年度間受給者数の2つ目の欄
-------------------------
```c
for( nenrei = UNDER_64 ; nenrei <= MAX_ROREI_JUKYU ; nenrei++ )
{
    if ( nenrei == UNDER_64 )
        for ( counter = 0 ; counter <= 1 ; counter++ )
            X[shubetu][sotai_nendo][counter] += （64歳と63歳の4本の和）;
    else
        X[shubetu][sotai_nendo][0] += （その年齢の2本の和）;
}
```

`counter` のループは**同じ式を2回足す**（右辺が `counter` に
依らない）ので、64歳のところだけ `[0]` と `[1]` の両方に入り、
65歳以上は `[0]` だけに足される。つまり

    [0] = 63〜115歳ぜんぶ
    [1] = 63・64歳だけ

になる。出力では「2欄」として並べて書かれる。

死亡一時金の足元に翌年度の値を入れる
------------------------------------
```c
if( nendo == SUIKEISHONENDO + 1 )
{
    Ichijikin[SHUBETU_SUM][1][NENREI_SUM - NENREI_SUM]
     = Ichijikin[SHUBETU_SUM][sotai_nendo][NENREI_SUM - NENREI_SUM];
}
```

添字 `1` は 2021年度（足元）。`sotai_nendo` は 2 なので、
**2022年度の計を 2021年度の欄に上書きする**。`dtst()` が足元の
死亡一時金を 0 にしているので、そのままだと `DOKUZI` の
2021年度の欄が 0 になる。それを避けるための埋め合わせと読める。

`for( nenrei )` の中にあるので年齢ごとに繰り返し代入されるが、
`Ichijikin[SHUBETU_SUM][sotai_nendo]` はその時点までの累計なので、
**最後の年齢まで足し終わった値**が残る。

使われない集計が3本ある
-----------------------
`Rorei_kiso_bunseki` `Shogai_kiso_bunseki` `Izoku_kiso_bunseki` は
局所配列で、100行ほどかけて埋めたあと**誰も読まない**。
出力にも出ない。`検証/原本の不具合.md` **F26**。

移植版も原本と同じ形で計算して `stat()` の戻り値として返す
（`_bunseki()`）。**原本の側は局所配列なのでハーネスから
出せず、C と突き合わせてはいない。** 消さずに残しているのは、
原本にある計算を落とさないため。
"""
import numpy as np

from setconst import (HIHO_NENREI_SUM, KURI_AGE_SAGE_SUM, MAX_HIHO_NENREI,
                      MAX_IZOKU_OTTO_JUKYU, MAX_IZOKU_TUMA_JUKYU,
                      MAX_ROREI_JUKYU, MAX_SHOGAI_JUKYU, MAX_SHUBETU,
                      MENJO_DANKAI, MIN_ROREI_JUKYU, NENREI_SUM,
                      SAISHUNENDO, SHONENDO, SHUBETU_ONNA, SHUBETU_OTOKO,
                      SHUBETU_SUM, SUIKEISAISHUNENDO, SUIKEISHONENDO, SUM,
                      UNDER_63, UNDER_64)
from stdfm import write_BeginData
from str_op import add

__all__ = ["stat", "Hanbetu"]

# `mfile_open.h` の出力番号
_KISONENKIN = 5
_DOKUZI = 6

# `snaps.h` の `#define HenkouSeinendo 1941`
_HENKOU_SEINENDO = 1941

_NENDO_N = SAISHUNENDO - SHONENDO + 1


def Hanbetu(shubetu):
    """stat.c:741 の忠実移植。種別を男女の計に振り分ける。"""
    return SHUBETU_OTOKO if shubetu <= 3 else SHUBETU_ONNA


def _e(v):
    """`fprintf( fp , "%20.14le" , v )` と同じ文字列。

    C の `%20.14le` は「指数部2桁以上・幅20で右詰め」。Python の
    `%.14e` は指数部2桁なので、幅だけ合わせれば同じになる。
    """
    return "%20.14e" % v


def stat(G, asctime=None):
    """stat.c:16 の忠実移植。"""
    # 局所配列（原本は `double X[2][106][2]`）
    def z2():
        return np.zeros((2, _NENDO_N, 2))

    Rorei_Jukyu_Nendokan = z2()
    Rorei_Kyu_Jukyu_Nendokan = z2()
    Turo_Kyu_Jukyu_Nendokan = z2()
    Gonen_Jukyu_Nendokan = z2()
    Shogai_Ippan_Jukyu_Nendokan = z2()
    Shogai_20mae_Jukyu_Nendokan = z2()
    Shogai_Kyu_Jukyu_Nendokan = z2()
    Izoku_Tuma_Jukyu_Nendokan = z2()
    Izoku_Otto_Jukyu_Nendokan = z2()
    Izoku_Ko_Jukyu_Nendokan = np.zeros((2, _NENDO_N))

    # ---- 年度間平均（前年度の「翌年度の率で見たぶん」と当年度） ----
    # **年度を降る**（`nendo--`）。`sotai_nendo - 1` を読むので、
    # 先に若い年度を書き換えると値が変わる
    for shubetu in range(1, MAX_SHUBETU):
        if shubetu not in (2, 3, 5, 6):
            continue

        for nendo in range(SUIKEISAISHUNENDO, SUIKEISHONENDO, -1):
            s = nendo - SHONENDO

            G.Hiho_Kei[shubetu, s, HIHO_NENREI_SUM] = (
                (G.Hiho_Kei[shubetu, s - 1, HIHO_NENREI_SUM]
                 + G.Hiho_Kei[shubetu, s, HIHO_NENREI_SUM]) / 2.)

            G.Hiho_Noufu[shubetu, s, HIHO_NENREI_SUM] = (
                (G.Hiho_Noufu_P[shubetu, s - 1, HIHO_NENREI_SUM]
                 + G.Hiho_Noufu[shubetu, s, HIHO_NENREI_SUM]) / 2.)

            for dankai in range(0, MENJO_DANKAI):
                G.Hiho_Menjo[shubetu, s, HIHO_NENREI_SUM, dankai] = (
                    (G.Hiho_Menjo_P[shubetu, s - 1, HIHO_NENREI_SUM,
                                    dankai]
                     + G.Hiho_Menjo[shubetu, s, HIHO_NENREI_SUM,
                                    dankai]) / 2.)

            G.Fuka_Hiho[shubetu, s, HIHO_NENREI_SUM] = (
                (G.Fuka_Hiho_P[shubetu, s - 1, HIHO_NENREI_SUM]
                 + G.Fuka_Hiho[shubetu, s, HIHO_NENREI_SUM]) / 2.)

        # ---- 男女の計と全体の計 ------------------------------------
        h = Hanbetu(shubetu)
        for nendo in range(SUIKEISHONENDO, SAISHUNENDO + 1):
            s = nendo - SHONENDO

            for jukyu_nenrei in range(MIN_ROREI_JUKYU, 70 + 1):
                j = jukyu_nenrei - MIN_ROREI_JUKYU
                for nenrei in range(UNDER_63, MAX_ROREI_JUKYU + 1):
                    n = nenrei - NENREI_SUM
                    for name in ("Rorei", "Rorei_Kyu", "Turo_Kyu",
                                 "Gonen"):
                        a = getattr(G, name)
                        a[h, s, n, KURI_AGE_SAGE_SUM] = add(
                            a[h, s, n, KURI_AGE_SAGE_SUM],
                            a[shubetu, s, n, j])

                    for name in ("Rorei", "Rorei_Kyu", "Turo_Kyu",
                                 "Gonen"):
                        a = getattr(G, name)
                        a[SHUBETU_SUM, s, 0, KURI_AGE_SAGE_SUM] = add(
                            a[SHUBETU_SUM, s, 0, KURI_AGE_SAGE_SUM],
                            a[shubetu, s, n, j])

            for nenrei in range(UNDER_63, MAX_SHOGAI_JUKYU + 1):
                n = nenrei - NENREI_SUM
                for name in ("Shogai_Ippan", "Shogai_20mae",
                             "Shogai_Kyu"):
                    a = getattr(G, name)
                    a[h, s, n] = add(a[h, s, n], a[shubetu, s, n])
                for name in ("Shogai_Ippan", "Shogai_20mae",
                             "Shogai_Kyu"):
                    a = getattr(G, name)
                    a[SHUBETU_SUM, s, 0] = add(a[SHUBETU_SUM, s, 0],
                                               a[shubetu, s, n])

            for nenrei in range(UNDER_63, MAX_IZOKU_TUMA_JUKYU + 1):
                n = nenrei - NENREI_SUM
                a = G.Izoku_Tuma
                a[h, s, n] = add(a[h, s, n], a[shubetu, s, n])
                a[SHUBETU_SUM, s, 0] = add(a[SHUBETU_SUM, s, 0],
                                           a[shubetu, s, n])

            for nenrei in range(UNDER_63, MAX_IZOKU_OTTO_JUKYU + 1):
                n = nenrei - NENREI_SUM
                a = G.Izoku_Otto
                a[h, s, n] = add(a[h, s, n], a[shubetu, s, n])
                a[SHUBETU_SUM, s, 0] = add(a[SHUBETU_SUM, s, 0],
                                           a[shubetu, s, n])

            G.Izoku_Ko[h, s] = add(G.Izoku_Ko[h, s],
                                   G.Izoku_Ko[shubetu, s])
            G.Izoku_Ko[SHUBETU_SUM, s] = add(G.Izoku_Ko[SHUBETU_SUM, s],
                                             G.Izoku_Ko[shubetu, s])

            G.Kafu[SHUBETU_SUM, s] = add(G.Kafu[SHUBETU_SUM, s],
                                         G.Kafu[shubetu, s])
            G.Kafu_Kyu[SHUBETU_SUM, s] = add(G.Kafu_Kyu[SHUBETU_SUM, s],
                                             G.Kafu_Kyu[shubetu, s])

            for nenrei in range(UNDER_63, MAX_HIHO_NENREI + 1):
                n = nenrei - NENREI_SUM
                G.Ichijikin[SHUBETU_SUM, s, 0] = add(
                    G.Ichijikin[SHUBETU_SUM, s, 0],
                    G.Ichijikin[shubetu, s, n])

                if nendo == SUIKEISHONENDO + 1:
                    # **2022年度の計を 2021年度の欄に上書きする**
                    G.Ichijikin[SHUBETU_SUM, 1, 0] = \
                        G.Ichijikin[SHUBETU_SUM, s, 0]

    # ---- 年度間受給者数 --------------------------------------------
    for shubetu in range(0, 1 + 1):
        a2 = shubetu * 3 + 2        # 第1号（2 or 5）
        a3 = shubetu * 3 + 3        # 第3号（3 or 6）
        for nendo in range(SAISHUNENDO, SUIKEISHONENDO - 1, -1):
            s = nendo - SHONENDO
            for nenrei in range(UNDER_64, MAX_ROREI_JUKYU + 1):
                n = nenrei - NENREI_SUM
                if nenrei == UNDER_64:
                    # 右辺は `counter` に依らないので [0] と [1] に
                    # 同じものが入る
                    for counter in range(0, 1 + 1):
                        for jukyu_nenrei in range(MIN_ROREI_JUKYU, 70 + 1):
                            j = jukyu_nenrei - MIN_ROREI_JUKYU
                            for dst, name in (
                                    (Rorei_Jukyu_Nendokan, "Rorei"),
                                    (Rorei_Kyu_Jukyu_Nendokan,
                                     "Rorei_Kyu"),
                                    (Turo_Kyu_Jukyu_Nendokan, "Turo_Kyu"),
                                    (Gonen_Jukyu_Nendokan, "Gonen")):
                                a = getattr(G, name)
                                dst[shubetu, s, counter] += (
                                    a[a2, s, n, j]["ninzu"]
                                    + a[a3, s, n, j]["ninzu"]
                                    + a[a2, s, n - 1, j]["ninzu"]
                                    + a[a3, s, n - 1, j]["ninzu"])

                        for dst, name in (
                                (Shogai_Ippan_Jukyu_Nendokan,
                                 "Shogai_Ippan"),
                                (Shogai_20mae_Jukyu_Nendokan,
                                 "Shogai_20mae"),
                                (Shogai_Kyu_Jukyu_Nendokan, "Shogai_Kyu"),
                                (Izoku_Tuma_Jukyu_Nendokan, "Izoku_Tuma"),
                                (Izoku_Otto_Jukyu_Nendokan,
                                 "Izoku_Otto")):
                            a = getattr(G, name)
                            dst[shubetu, s, counter] += (
                                a[a2, s, n]["ninzu"]
                                + a[a3, s, n]["ninzu"]
                                + a[a2, s, n - 1]["ninzu"]
                                + a[a3, s, n - 1]["ninzu"])

                    Izoku_Ko_Jukyu_Nendokan[shubetu, s] += (
                        G.Izoku_Ko[a2, s]["ninzu"]
                        + G.Izoku_Ko[a3, s]["ninzu"])
                else:
                    for jukyu_nenrei in range(MIN_ROREI_JUKYU, 70 + 1):
                        j = jukyu_nenrei - MIN_ROREI_JUKYU
                        for dst, name in (
                                (Rorei_Jukyu_Nendokan, "Rorei"),
                                (Rorei_Kyu_Jukyu_Nendokan, "Rorei_Kyu"),
                                (Turo_Kyu_Jukyu_Nendokan, "Turo_Kyu"),
                                (Gonen_Jukyu_Nendokan, "Gonen")):
                            a = getattr(G, name)
                            dst[shubetu, s, 0] += (
                                a[a2, s, n, j]["ninzu"]
                                + a[a3, s, n, j]["ninzu"])

                    for dst, name in (
                            (Shogai_Ippan_Jukyu_Nendokan, "Shogai_Ippan"),
                            (Shogai_20mae_Jukyu_Nendokan, "Shogai_20mae"),
                            (Shogai_Kyu_Jukyu_Nendokan, "Shogai_Kyu"),
                            (Izoku_Tuma_Jukyu_Nendokan, "Izoku_Tuma"),
                            (Izoku_Otto_Jukyu_Nendokan, "Izoku_Otto")):
                        a = getattr(G, name)
                        dst[shubetu, s, 0] += (a[a2, s, n]["ninzu"]
                                               + a[a3, s, n]["ninzu"])

    # ---- 試算の内容（出力の先頭に書く） ----------------------------
    Shisan_Naiyou = ""
    Shisan_Naiyou += "Kisai_Shitasasae , %f\n" % G.Kisai_Shitasasae
    Shisan_Naiyou += "HenkouSeinendo , %d\n" % _HENKOU_SEINENDO
    Shisan_Naiyou += "Kako_Saimu , %d\n" % G.Kako_Saimu
    Shisan_Naiyou += "Kugiri_Nendo , %d\n" % G.Kugiri_Nendo
    Shisan_Naiyou += "Jyukyusha_Nomi , %d\n" % G.Jyukyusha_Nomi

    # ---- 使われない集計（F26。原本と同じ形で計算する） ------------
    bunseki = _bunseki(G)

    # ---- KISONENKIN（④基礎年金が読む） ----------------------------
    fp = G.fp_out[_KISONENKIN]
    write_BeginData(G.Version, Shisan_Naiyou, fp, asctime)

    for nendo in range(SHONENDO, SAISHUNENDO + 1):
        s = nendo - SHONENDO

        for nenrei in range(UNDER_63, MAX_ROREI_JUKYU + 1):
            n = nenrei - NENREI_SUM
            K = KURI_AGE_SAGE_SUM

            # 1-1 新法老齢基礎
            for shubetu in range(SHUBETU_OTOKO, SHUBETU_ONNA + 1):
                r = G.Rorei[shubetu, s, n, K]
                fp.write("%d,%d,%d,%d,%d,%d," % (nendo, 1, nenrei, 1, 1,
                                                 shubetu - 6))
                fp.write(_e(r["noufu"]) + ",")
                fp.write(_e(r["menjo"][SUM, 1] + r["rofuku_shitasasae"])
                         + ",")
                fp.write(_e(r["menjo"][SUM, 2]) + ",")
                fp.write(_e(0.) + "\n")

            # 1-2 新法障害基礎
            for shubetu in range(SHUBETU_OTOKO, SHUBETU_ONNA + 1):
                ip = G.Shogai_Ippan[shubetu, s, n]
                mn = G.Shogai_20mae[shubetu, s, n]
                fp.write("%d,%d,%d,%d,%d,%d," % (nendo, 1, nenrei, 1, 2,
                                                 shubetu - 6))
                fp.write(_e(ip["kihon"]) + ",")
                fp.write(_e(ip["kakyu"]) + ",")
                fp.write(_e(0.) + ",")
                fp.write(_e(mn["kihon"]) + ",")
                fp.write(_e(mn["kakyu"]) + "\n")

            # 1-3 新法遺族基礎
            for shubetu in range(SHUBETU_OTOKO, SHUBETU_ONNA + 1):
                tu = G.Izoku_Tuma[shubetu, s, n]
                ot = G.Izoku_Otto[shubetu, s, n]
                ko = G.Izoku_Ko[shubetu, s]
                fp.write("%d,%d,%d,%d,%d,%d," % (nendo, 1, nenrei, 1, 3,
                                                 shubetu - 6))
                fp.write(_e(tu["kihon"] + ot["kihon"]
                            + (ko["kihon"] if nenrei == UNDER_63 else 0.))
                         + ",")
                fp.write(_e(tu["kakyu"] + ot["kakyu"]
                            + (ko["kakyu"] if nenrei == UNDER_63 else 0.))
                         + "\n")

            # 2-1 旧法老齢（老齢＋通算老齢）と5年年金
            for shubetu in range(SHUBETU_OTOKO, SHUBETU_ONNA + 1):
                rk = G.Rorei_Kyu[shubetu, s, n, K]
                tk = G.Turo_Kyu[shubetu, s, n, K]
                fp.write("%d,%d,%d,%d,%d,%d," % (nendo, 1, nenrei, 2, 1,
                                                 shubetu - 6))
                fp.write(_e(rk["noufu"] + tk["noufu"]) + ",")
                fp.write(_e(rk["menjo"] + tk["menjo"]) + ",")
                fp.write(_e(rk["kasa_noufu"] + tk["kasa_noufu"]) + ",")
                fp.write(_e(rk["kasa_menjo"] + tk["kasa_menjo"]) + ",")
                fp.write(_e(rk["rofuku_shitasasae"]
                            + tk["rofuku_shitasasae"]) + ",")
                fp.write(_e(G.Gonen[shubetu, s, n, K]["noufu"]) + "\n")

            # 2-2 旧法障害
            for shubetu in range(SHUBETU_OTOKO, SHUBETU_ONNA + 1):
                sk = G.Shogai_Kyu[shubetu, s, n]
                fp.write("%d,%d,%d,%d,%d,%d," % (nendo, 1, nenrei, 2, 2,
                                                 shubetu - 6))
                fp.write(_e(sk["kihon"] - sk["menjo_kihon"]) + ",")
                fp.write(_e(sk["menjo_kihon"]) + ",")
                fp.write(_e(sk["kakyu"] - sk["menjo_kakyu"]) + ",")
                fp.write(_e(sk["menjo_kakyu"]) + "\n")

            # 2-3 旧法遺族（**全部 0**。③は旧法遺族を推計しない）
            for shubetu in range(SHUBETU_OTOKO, SHUBETU_ONNA + 1):
                fp.write("%d,%d,%d,%d,%d,%d," % (nendo, 1, nenrei, 2, 3,
                                                 shubetu - 6))
                fp.write(_e(0.) + "," + _e(0.) + "," + _e(0.) + ","
                         + _e(0.) + "\n")

        # 保険料の納付月数（第1号男・女）＋産前産後・育児期間の免除
        fp.write("%d," % nendo)
        for shubetu in (2, 5):
            v = G.Hiho_Noufu[shubetu, s, HIHO_NENREI_SUM]
            for dankai in range(1, MENJO_DANKAI):
                v += (G.Hiho_Menjo[shubetu, s, HIHO_NENREI_SUM, dankai]
                      * G.Hokenryou_Wariai[dankai])
            fp.write(_e(v) + ("," if shubetu == 2 else ""))
        fp.write("," + _e(G.Hiho_Sankyu_Sum[s]))
        fp.write("," + _e(G.Hiho_Ikukyu_Sum[s]))
        fp.write("\n")

        # 2-1 年度間受給者数（老齢）
        for shubetu in range(0, 1 + 1):
            fp.write("%d,%d,%d,%d," % (nendo, 2, 1, shubetu + 1))
            for counter in range(0, 1 + 1):
                fp.write(_e(Rorei_Jukyu_Nendokan[shubetu, s, counter])
                         + ",")
            for counter in range(0, 1 + 1):
                fp.write(_e(0.) + ",")
            for counter in range(0, 1 + 1):
                fp.write(_e(Rorei_Kyu_Jukyu_Nendokan[shubetu, s, counter])
                         + ",")
            for counter in range(0, 1 + 1):
                fp.write(_e(Turo_Kyu_Jukyu_Nendokan[shubetu, s, counter])
                         + ",")
            fp.write(_e(Gonen_Jukyu_Nendokan[shubetu, s, 0]) + "\n")

        # 2-2 年度間受給者数（障害）
        for shubetu in range(0, 1 + 1):
            fp.write("%d,%d,%d,%d," % (nendo, 2, 2, shubetu + 1))
            for counter in range(0, 1 + 1):
                fp.write(_e(
                    Shogai_Ippan_Jukyu_Nendokan[shubetu, s, counter]
                    + Shogai_20mae_Jukyu_Nendokan[shubetu, s, counter])
                    + ",")
            fp.write(_e(Shogai_Kyu_Jukyu_Nendokan[shubetu, s, 0]) + ",")
            fp.write(_e(Shogai_Kyu_Jukyu_Nendokan[shubetu, s, 1]) + "\n")

        # 2-3 年度間受給者数（遺族）
        fp.write("%d,%d,%d,%d," % (nendo, 2, 3, 1))
        ko = Izoku_Ko_Jukyu_Nendokan[0, s] + Izoku_Ko_Jukyu_Nendokan[1, s]
        fp.write(_e(ko) + ",")
        fp.write(_e(ko) + "\n")

        fp.write("%d,%d,%d,%d," % (nendo, 2, 3, 2))
        for counter in range(0, 1 + 1):
            v = (Izoku_Tuma_Jukyu_Nendokan[0, s, counter]
                 + Izoku_Tuma_Jukyu_Nendokan[1, s, counter]
                 + Izoku_Otto_Jukyu_Nendokan[0, s, counter]
                 + Izoku_Otto_Jukyu_Nendokan[1, s, counter]
                 + Izoku_Ko_Jukyu_Nendokan[0, s]
                 + Izoku_Ko_Jukyu_Nendokan[1, s])
            fp.write(_e(v) + ("," if counter == 0 else "\n"))

    # ---- DOKUZI（独自給付） ----------------------------------------
    fp = G.fp_out[_DOKUZI]
    write_BeginData(G.Version, Shisan_Naiyou, fp, asctime)

    K = KURI_AGE_SAGE_SUM
    for nendo in range(SHONENDO, SAISHUNENDO + 1):
        s = nendo - SHONENDO
        r = G.Rorei[SHUBETU_SUM, s, 0, K]
        rk = G.Rorei_Kyu[SHUBETU_SUM, s, 0, K]
        tk = G.Turo_Kyu[SHUBETU_SUM, s, 0, K]
        sk = G.Shogai_Kyu[SHUBETU_SUM, s, 0]
        kf = G.Kafu[SHUBETU_SUM, s]
        kk = G.Kafu_Kyu[SHUBETU_SUM, s]
        ic = G.Ichijikin[SHUBETU_SUM, s, 0]

        fp.write("%d," % nendo)
        fp.write(_e(G.Fuka_Hiho[2, s, HIHO_NENREI_SUM]
                    + G.Fuka_Hiho[5, s, HIHO_NENREI_SUM]) + ",")
        fp.write(_e(r["fuka"]) + ",")
        fp.write(_e(rk["fuka"]) + ",")
        fp.write(_e(tk["fuka"]) + ",")
        fp.write(_e(kf["noufu"] + kf["menjo"][SUM, SUM]) + ",")
        fp.write(_e(kk["noufu"]) + ",")
        fp.write(_e(kk["menjo"][SUM, SUM]) + ",")
        fp.write(_e(ic["kyufu"]) + ",")
        fp.write(_e(ic["kyufu_fuka"]) + ",")
        fp.write(_e(r["menjo"][SUM, SUM]
                    + rk["menjo"] + rk["kasa_menjo"]
                    + tk["menjo"] + tk["kasa_menjo"]
                    + sk["menjo_kihon"] + sk["menjo_kakyu"]) + "\n")

    return bunseki


def _bunseki(G):
    """`stat.c:378-479` の忠実移植。**誰も読まない集計3本**（F26）。

    局所配列に 100行ほどかけて積むが、出力にも他の関数にも出ない。
    原本の側は局所なのでハーネスから出せず、**C との突き合わせは
    できていない**。原本にある計算を落とさないために残している。
    """
    Rorei_kiso = np.zeros((_NENDO_N, 2))
    Shogai_kiso = np.zeros((_NENDO_N, 2, 2))
    Izoku_kiso = np.zeros((_NENDO_N, 2, 2))
    K = KURI_AGE_SAGE_SUM

    for seibetu in range(0, 2):
        sh = SHUBETU_OTOKO if seibetu == 0 else SHUBETU_ONNA
        for nendo in range(SHONENDO, SAISHUNENDO + 1):
            for nenrei in range(UNDER_63, MAX_ROREI_JUKYU + 1):
                s = nendo - SHONENDO
                r = G.Rorei[sh, s, nenrei - NENREI_SUM, K]
                # 原本は4回に分けて足す（足す順をそのまま写す）
                Rorei_kiso[s, seibetu] += r["noufu"]
                Rorei_kiso[s, seibetu] += r["menjo"][SUM, 1]
                Rorei_kiso[s, seibetu] += r["rofuku_shitasasae"]
                Rorei_kiso[s, seibetu] += r["menjo"][SUM, 2]

    for seibetu in range(0, 2):
        sh = SHUBETU_OTOKO if seibetu == 0 else SHUBETU_ONNA
        for kubun in range(0, 2):
            for nendo in range(SHONENDO, SAISHUNENDO + 1):
                for nenrei in range(UNDER_63, MAX_ROREI_JUKYU + 1):
                    s = nendo - SHONENDO
                    n = nenrei - NENREI_SUM
                    f = "kihon" if kubun == 0 else "kakyu"
                    Shogai_kiso[s, seibetu, kubun] += \
                        G.Shogai_Ippan[sh, s, n][f]
                    Shogai_kiso[s, seibetu, kubun] += \
                        G.Shogai_20mae[sh, s, n][f]

    for seibetu in range(0, 2):
        for kubun in range(0, 2):
            for nendo in range(SHONENDO, SAISHUNENDO + 1):
                for nenrei in range(UNDER_63, MAX_ROREI_JUKYU + 1):
                    s = nendo - SHONENDO
                    n = nenrei - NENREI_SUM
                    f = "kihon" if kubun == 0 else "kakyu"
                    if seibetu == 0:
                        # 男の欄に**女の夫遺族**と**男の子遺族**を足す
                        Izoku_kiso[s, 0, kubun] += \
                            G.Izoku_Otto[SHUBETU_ONNA, s, n][f]
                        Izoku_kiso[s, 0, kubun] += (
                            G.Izoku_Ko[SHUBETU_OTOKO, s][f]
                            if nenrei == UNDER_63 else 0.)
                    if seibetu == 1:
                        Izoku_kiso[s, 1, kubun] += \
                            G.Izoku_Tuma[SHUBETU_OTOKO, s, n][f]

    return {"Rorei_kiso_bunseki": Rorei_kiso,
            "Shogai_kiso_bunseki": Shogai_kiso,
            "Izoku_kiso_bunseki": Izoku_kiso}
