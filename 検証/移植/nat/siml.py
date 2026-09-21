# -*- coding: utf-8 -*-
"""
国民年金/siml.c の忠実移植（1年度ぶんの推計）
=============================================
1,548 行。③の心臓部。`main.c` が種別ごとに

```c
for( nendo = SUIKEISHONENDO + 1 ; nendo <= SUIKEISAISHUNENDO ; nendo++ ) {
    siml( nendo , shubetu );
    shke( nendo , shubetu );
}
```

の形で **104回** 呼ぶ（2022〜2125年度）。前年度の `*_Nendomatu`
（年度末の人数と年金額）から当年度のそれを作る。

おおまかな流れ

1. 納付状況（`Noufu_Jokyo`）を当年度の納付率から組む
2. 被保険者・待期者を1年進める（残存 → 外枠に合わせる → 新規加入）
3. 構造体の中身（期間・納付月数・免除月数）を人数で加重平均する
4. 障害・遺族・寡婦・死亡一時金の**新規発生**を出す
5. 老齢基礎の**新規裁定**を出す（待期者から）
6. 全部の `*_Nendomatu` を「前年度 × (1 - 失権率) × 改定率 + 新規」にする

原本が配列の外を読むところが2か所
---------------------------------
**どちらも `_c_at()` を通して、C と同じ「行優先で足すだけ」の
番地計算を再現している。** NumPy はそのままでは

- 負の添字を**折り返す**（`a[-1]` は最後の要素）
- 上限を超えると**例外**になる

ので、素直に書くと C と違う値になる。

### (1) 20歳のときに1つ前の年齢を読む（`siml.c:328-349`）

```c
Hasseisha_Shogai[nenrei - MIN_HIHO_NENREI][kikan]
 = Hihokensha[nendo - 1 - SHONENDO][nenrei - 1 - MIN_HIHO_NENREI][kikan - 1].ninzu
    * Hasseiryoku_Shogai[sotai_nendo][nenrei - MIN_HIHO_NENREI];
```

`nenrei` が `MIN_HIHO_NENREI`（20歳）のとき2番目の添字が **-1**。
すぐ上の `Hiho_Zanzon` と `Dattaisha_Gokei` には
`if( nenrei == MIN_HIHO_NENREI )` の守りがあるのに、
`Hasseisha_Shogai` と `Hihokensha_Shibou` には無い。

`Hihokensha` は `[106][51][51]` なので、C の番地計算では

    Hihokensha[y][-1][k]  →  Hihokensha[y - 1][50][k]

つまり**2年前の70歳**の人数を読む。

**出力には出ない。** `Hihokensha[…][70歳][…]` は全部の年度で 0 に
なる。理由は3つ重なっている。

1. 足元（`dtst`）は 20〜**69歳**しか読まない
2. `kiso` が 65歳以上の脱退力を 1 にするので残存が 0
3. 外枠（①被保険者推計）の**70歳の第1号は 4種別とも全年度 0**
   （実測。`Sotowaku[shubetu][*][70 - MIN_WAKU_NENREI]` の非零が 0本）
   なので新規加入も 0

30年ぶん走らせて「20歳のとき 0 を読む」版と突き合わせ、
160項目すべて一致することを確かめた。入力の70歳の第1号が 0 で
なくなれば結果が変わる。`検証/原本の不具合.md` **B10**。

### (2) 生命表の性別の添字が1つずれている（`siml.c:638, 692, 753`）

```c
q[( nendo <= SHIKKENRITU_MAX ? nendo : SHIKKENRITU_MAX ) - SHIKKENRITU_MIN][nenrei][seibetu]
```

`seibetu` は `OTOKO` = **1** / `ONNA` = **2**（`snaps.h`）。
`q` は `[52][115][2]` なので3番目の添字は **0（男）/ 1（女）**。
`kiso.c` はちゃんと `q[…][…][0]` / `[1]` を使っている。

    seibetu = 1（男）→ q[…][nenrei][1]     女の死亡率を読む
    seibetu = 2（女）→ q[…][nenrei][2]     配列の外 = q[…][nenrei + 1][0]

効くのは 60〜64歳の遺族（妻・夫・子）の新規発生だけだが、
**出力に出る**。`[seibetu - 1]` に直した版と突き合わせると
6年ぶんで 10項目が動き、第1号男（種別2）の遺族基礎（妻）の
年度末人数（全年齢の合計）は

    FY2022  7,795.59 → 7,825.56  (+0.38%)
    FY2031  4,318.46 → 4,391.79  (+1.70%)
    FY2041  2,691.87 → 2,744.54  (+1.96%)

と増える。60〜64歳では男の死亡率が女より高いので、男の推計で
女の列を読むと**低めに出る**。符号も筋が通っている。同 **B11**。

再加入は必ず 0
--------------
```c
Saikanyu_Gokei
 = min( ( Sotowaku[…] - Hiho_Zanzon_Gokei ) * Saikanyuritu[sotai_nendo][…] ,
        Taiki_Zanzon_Gokei );
```

`Saikanyuritu` は **`kiso.c:79` で 0 に埋められるだけで、
16本の .c のどこにも値が入らない**。入力ファイルも無い。
だから `Saikanyu_Gokei` は必ず 0（`Taiki_Zanzon_Gokei` が
負にならないので `min` は 0 を採る）で、待期者から被保険者への
**再加入は1人も起きない**。同 **D6**。

原本どおりに写してあるので、`Saikanyu` が絡む項
（`scalar( Saikanyu , Taiki_Zennen )` など）も 0 のまま残している。

`static` の局所配列
-------------------
```c
static double Hiho_Zanzon[51][51];
…
static double Hasseisha_Shogai[51][51];
```

7本が `static`（呼び出しをまたいで残る）。ただし**どれも1回の
呼び出しの中で全要素が書かれてから読まれる**ので、`static` で
なくても結果は同じ。原本に合わせて `G` に持たせた。

受給年齢の軸をまとめて計算している
----------------------------------
遺族（妻・夫・子）と寡婦の新規発生は

```c
for( nenrei ) for( nenrei_tuma ) for( kikan ) { … += … }
```

の3重ループで、`nenrei_tuma` が 100通り・`kikan` が 51通りある。
**`nenrei_tuma` を NumPy の軸にまとめた。** ある `nenrei_tuma` に
足し込む順番は「`nenrei` が外・`kikan` が内」のままなので、
浮動小数の足す順は原本と同じ（ビット一致する）。

`Noufu_Kikan` の計算は `nenrei_tuma` に依らないので
`nenrei_tuma` のループの外に出した（同じ式を同じ順で1回だけ
計算するので値は変わらない）。
"""
import numpy as np

from setconst import (ECON_SHONENDO, KOKKO_HIKIAGE, MAX_HIHO_KIKAN,
                      MAX_HIHO_NENREI, MAX_IZOKU_KO_JUKYU,
                      MAX_IZOKU_OTTO_JUKYU, MAX_IZOKU_TUMA_JUKYU,
                      MAX_KAFU_JUKYU, MAX_ROREI_JUKYU, MAX_SHOGAI_JUKYU,
                      MENJO_1_4, MENJO_DANKAI, MENJO_HOUTEI, MENJO_SHINSEI,
                      MIN_HIHO_NENREI, MIN_IZOKU_KO_JUKYU,
                      MIN_IZOKU_OTTO_JUKYU, MIN_IZOKU_TUMA_JUKYU,
                      MIN_KAFU_JUKYU, MIN_ROREI_JUKYU, MIN_SHOGAI_JUKYU,
                      MIN_WAKU_NENREI, N_O_NENDO, NOUFU, ONNA,
                      OP_MAX_KYOSHUTU_NENREI, OTOKO, GAKUSEI,
                      SHIKKENRITU_MAX, SHIKKENRITU_MIN,
                      SHOGAI_TOKYU, SHONENDO, SOTOWAKU_SHONENDO,
                      SUIKEISHONENDO, UNDER_67, WAKAMONO, ZENGAKU)
from stdfm import NatError, extenda, extendb, extendc, nenkin_fdiv
from str_op import (add, adjustbenefit, average_by_ninzu, multiply, scalar,
                    scalar_2,
                    # 軸をまとめて処理する版（速度のため。原本には無い）
                    add_arr, adjustbenefit_arr, average_by_ninzu_arr,
                    multiply_arr, scalar_arr, scalar_2_arr)

__all__ = ["siml", "Shibou_Kubun", "Nendomatu_Tyousei_Keisu"]

_HIHO_N = MAX_HIHO_NENREI - MIN_HIHO_NENREI + 1     # 51
_KIKAN_N = MAX_HIHO_KIKAN + 1                       # 51


def _c_at(a, *idx):
    """C の多次元配列と同じ番地計算（境界を見ない）。

    原本が配列の外を読むところだけで使う。詳しくは冒頭の解説。
    """
    n = 0
    for i, k in enumerate(idx):
        n = n * a.shape[i] + k
    return a.reshape(-1)[n]


def _val(x, dt):
    """構造体1個の写しを作る（原本の**値渡し**に相当）。

    原本は `Hiho_Zennen` に代入してから `.ninzu` を書き換えるので、
    元の配列は変わらない。NumPy の `arr[i]` はビューなので、
    写しを作らないと元を壊す。
    """
    out = np.zeros((), dtype=dt)
    out[()] = x
    return out


def _statics(G):
    """原本の `static` な局所配列を用意する（呼び出しをまたいで残る）。"""
    s = getattr(G, "_siml_static", None)
    if s is None:
        s = {}
        for n in ("Hiho_Zanzon", "Taiki_Zanzon", "Saikanyu",
                  "Dattaisha_Gokei", "Dattaisha_Seizon",
                  "Hasseisha_Shogai"):
            s[n] = np.zeros((_HIHO_N, _KIKAN_N))
        s["Shinkikanyu"] = np.zeros(_HIHO_N)
        G._siml_static = s
    return s


def Shibou_Kubun(G, nendo, noufu_kikan, option):
    """siml.c:1470 の忠実移植。死亡一時金の納付月数の区分。"""
    if noufu_kikan < 15.:
        kubun = 0
    elif noufu_kikan < 20.:
        kubun = 1
    elif noufu_kikan < 25.:
        kubun = 2
    elif noufu_kikan < 30.:
        kubun = 3
    elif noufu_kikan < 35.:
        kubun = 4
    elif noufu_kikan < 40.:
        kubun = 5
    else:
        if option == 1 and nendo >= G.OPTION_START:
            kubun = 6
        else:
            kubun = 5
    return kubun


def Nendomatu_Tyousei_Keisu(G, nendo, nenrei):
    """siml.c:1516 の忠実移植。45年化で年金額を割り増す係数。

    原本は `41 / 40.` と書く（後ろが `double` なので整数除算には
    ならない）。
    """
    k = G.OP_HIKIAGE_KANKAKU
    if nendo == G.OPTION_START and nenrei <= 60:
        fraction = 41 / 40.
    elif nendo == G.OPTION_START + k and nenrei <= 61:
        fraction = 42 / 41.
    elif nendo == G.OPTION_START + k * 2 and nenrei <= 62:
        fraction = 43 / 42.
    elif nendo == G.OPTION_START + k * 3 and nenrei <= 63:
        fraction = 44 / 43.
    elif nendo == G.OPTION_START + k * 4 and nenrei <= 64:
        fraction = 45 / 44.
    else:
        fraction = 1.
    return fraction


def siml(G, nendo, shubetu):
    """siml.c:21 の忠実移植。"""
    st = _statics(G)
    Hiho_Zanzon = st["Hiho_Zanzon"]
    Taiki_Zanzon = st["Taiki_Zanzon"]
    Saikanyu = st["Saikanyu"]
    Shinkikanyu = st["Shinkikanyu"]
    Dattaisha_Gokei = st["Dattaisha_Gokei"]
    Dattaisha_Seizon = st["Dattaisha_Seizon"]
    Hasseisha_Shogai = st["Hasseisha_Shogai"]

    HH = G.Hihokensha.dtype
    Noufu_Jokyo = np.zeros(_HIHO_N, dtype=HH)
    Hihokensha_Shibou = np.zeros((_HIHO_N, _KIKAN_N), dtype=HH)
    Taikisha_Shibou = np.zeros((_HIHO_N, _KIKAN_N), dtype=HH)

    # 原本の `Hiho_Zanzon_P` `Taiki_Zanzon_P` は宣言だけで使われない
    # （`= {0.}` で 0 にしたあと誰も読まない）。移植版では作らない
    Hiho_Zanzon2 = np.zeros((_HIHO_N, _KIKAN_N))
    Shinkikanyu2 = np.zeros(_HIHO_N)
    Hiho_Zanzon_Gokei2 = 0.

    Rorei_Shinki = np.zeros(G.Rorei_Shinki2.shape[0], dtype=G.Rorei.dtype)
    _SG_N = MAX_SHOGAI_JUKYU - MIN_SHOGAI_JUKYU + 1
    SD = G.Shogai_Ippan_Nendomatu.dtype
    ID = G.Izoku_Tuma_Nendomatu.dtype
    KD = G.Kafu_Nendomatu.dtype
    Shogai_Ippan_Shinki = np.zeros((_SG_N, SHOGAI_TOKYU), dtype=SD)
    Shogai_20mae_Shinki = np.zeros((_SG_N, SHOGAI_TOKYU), dtype=SD)
    Izoku_Tuma_Shinki = np.zeros(
        MAX_IZOKU_TUMA_JUKYU - MIN_IZOKU_TUMA_JUKYU + 1, dtype=ID)
    Izoku_Otto_Shinki = np.zeros(
        MAX_IZOKU_OTTO_JUKYU - MIN_IZOKU_OTTO_JUKYU + 1, dtype=ID)
    Izoku_Ko_Shinki = np.zeros(
        MAX_IZOKU_KO_JUKYU - MIN_IZOKU_KO_JUKYU + 1, dtype=ID)
    Kafu_Shinki = np.zeros(MAX_KAFU_JUKYU - MIN_KAFU_JUKYU + 1, dtype=KD)

    sotai_nendo = nendo - SHONENDO
    if sotai_nendo < 0:
        raise NatError("年度エラー")

    if shubetu == 2 or shubetu == 3:
        seibetu = OTOKO
    elif shubetu == 5 or shubetu == 6:
        seibetu = ONNA
    else:
        seibetu = 0

    y1 = nendo - 1 - SHONENDO           # 前年度の添字
    yq = (nendo if nendo <= SHIKKENRITU_MAX else SHIKKENRITU_MAX) \
        - SHIKKENRITU_MIN

    # ---- 納付状況 --------------------------------------------------
    if G.Kako_Saimu == 0 or nendo <= G.Kugiri_Nendo:
        for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
            i = nenrei - MIN_HIHO_NENREI
            nj = Noufu_Jokyo[i]
            nj["ninzu"] = 0.
            nj["kikan"] = 1.
            nj["noufu"] = G.Noufuritu[shubetu, sotai_nendo, i, NOUFU]

            zen = (G.Noufuritu[shubetu, sotai_nendo, i, MENJO_HOUTEI]
                   + G.Noufuritu[shubetu, sotai_nendo, i, MENJO_SHINSEI])
            m = nj["menjo"]
            for dankai in range(0, MENJO_DANKAI):
                for kokko in range(0, KOKKO_HIKIAGE - 1 + 1):
                    if dankai == ZENGAKU:
                        m[dankai, kokko] = zen
                    else:
                        m[dankai, kokko] = G.Noufuritu[
                            shubetu, sotai_nendo, i, dankai]

            nj["gakusei"] = G.Noufuritu[shubetu, sotai_nendo, i, GAKUSEI]
            nj["wakamono"] = G.Noufuritu[shubetu, sotai_nendo, i, WAKAMONO]
            nj["fuka"] = G.Noufuritu_Fuka[shubetu, sotai_nendo, i]
    else:
        # 過去債務の推計では納付をぜんぶ 0 にする（期間だけ 1）
        for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
            i = nenrei - MIN_HIHO_NENREI
            Noufu_Jokyo[i] = np.zeros((), dtype=HH)
            Noufu_Jokyo[i]["kikan"] = 1.

    # ---- 被保険者・待期者を1年進める --------------------------------
    for nenrei in range(MAX_HIHO_NENREI, MIN_HIHO_NENREI - 1, -1):
        i = nenrei - MIN_HIHO_NENREI

        Hiho_Zanzon_Gokei = 0.
        Hiho_Zanzon[i, 0] = 0.

        for kikan in range(1, MAX_HIHO_KIKAN + 1):
            if nenrei == MIN_HIHO_NENREI:
                Hiho_Zanzon[i, kikan] = 0.
            else:
                Hiho_Zanzon[i, kikan] = \
                    G.Hihokensha[y1, i - 1, kikan - 1]["ninzu"]

                if kikan == MAX_HIHO_KIKAN:
                    Hiho_Zanzon[i, kikan] += \
                        G.Hihokensha[y1, i - 1, kikan]["ninzu"]

                Hiho_Zanzon[i, kikan] *= (1. - G.Dattairyoku_Gokei[
                    sotai_nendo, i])

            Hiho_Zanzon_Gokei += Hiho_Zanzon[i, kikan]

        Taiki_Zanzon_Gokei = 0.

        for kikan in range(0, MAX_HIHO_KIKAN + 1):
            if nenrei == MIN_HIHO_NENREI:
                Taiki_Zanzon[i, kikan] = 0.
                Taikisha_Shibou[i, kikan]["ninzu"] = 0.
            else:
                Taiki_Zanzon[i, kikan] = \
                    (G.Taikisha[y1, i - 1, kikan]["ninzu"]
                     * (1. - G.Shikkenritu_Rorei[sotai_nendo, i]))

                Taikisha_Shibou[i, kikan]["ninzu"] = \
                    (G.Taikisha[y1, i - 1, kikan]["ninzu"]
                     - Taiki_Zanzon[i, kikan])

            Taiki_Zanzon_Gokei += Taiki_Zanzon[i, kikan]

        if G.Option == 1:
            # 45年化の「延長ぶん」（60歳以降の第1号）
            Hiho_Zanzon_Gokei2 = 0.
            Hiho_Zanzon2[i, 0] = 0.

            for kikan in range(1, MAX_HIHO_KIKAN - 1 + 1):
                if nenrei == MIN_HIHO_NENREI:
                    Hiho_Zanzon2[i, kikan] = 0.
                else:
                    Hiho_Zanzon2[i, kikan] = \
                        G.Hihokensha2[y1, i - 1, kikan - 1]["ninzu"]

                    # 原本の `if( kikan == MAX_HIHO_KIKAN )` はこのループ
                    # では起きない（上限が `MAX_HIHO_KIKAN - 1`）
                    if kikan == MAX_HIHO_KIKAN:
                        Hiho_Zanzon2[i, kikan] += \
                            G.Hihokensha2[y1, i - 1, kikan]["ninzu"]

                    Hiho_Zanzon2[i, kikan] *= \
                        (1. - G.Shikkenritu_Rorei[sotai_nendo, i])

                Hiho_Zanzon_Gokei2 += Hiho_Zanzon2[i, kikan]

        waku = G.Sotowaku[shubetu, nendo - SOTOWAKU_SHONENDO,
                          nenrei - MIN_WAKU_NENREI]

        if G.Option == 1 and extenda(G, nendo, nenrei) != 1:
            if waku < Hiho_Zanzon_Gokei + Hiho_Zanzon_Gokei2:
                r = nenkin_fdiv(waku - Hiho_Zanzon_Gokei2,
                                Hiho_Zanzon_Gokei)
                for kikan in range(0, MAX_HIHO_KIKAN + 1):
                    Hiho_Zanzon[i, kikan] *= r
        else:
            if waku < Hiho_Zanzon_Gokei:
                r = nenkin_fdiv(waku, Hiho_Zanzon_Gokei)
                for kikan in range(0, MAX_HIHO_KIKAN + 1):
                    Hiho_Zanzon[i, kikan] *= r

        # `Saikanyuritu` は 0 のままなので必ず 0（D6）
        Saikanyu_Gokei = min((waku - Hiho_Zanzon_Gokei)
                             * G.Saikanyuritu[sotai_nendo, i],
                             Taiki_Zanzon_Gokei)

        r = nenkin_fdiv(Saikanyu_Gokei, Taiki_Zanzon_Gokei)
        for kikan in range(0, MAX_HIHO_KIKAN + 1):
            Saikanyu[i, kikan] = Taiki_Zanzon[i, kikan] * r
            Taiki_Zanzon[i, kikan] -= Saikanyu[i, kikan]

        Shinkikanyu[i] = waku - Saikanyu[i, 0]

        ext_b = (G.Option == 1 and extendb(G, nendo, nenrei) == 1)
        for kikan in range(1, MAX_HIHO_KIKAN + 1):
            Shinkikanyu[i] -= Hiho_Zanzon[i, kikan] + Saikanyu[i, kikan]

            if ext_b:
                Shinkikanyu[i] -= Hiho_Zanzon2[i, kikan]

        for kikan in range(MAX_HIHO_KIKAN, 0, -1):
            G.Hihokensha[sotai_nendo, i, kikan]["ninzu"] = \
                Hiho_Zanzon[i, kikan] + Saikanyu[i, kikan]

            if G.Option == 1:
                if nenrei <= OP_MAX_KYOSHUTU_NENREI:
                    G.Hihokensha2[sotai_nendo, i, kikan]["ninzu"] = \
                        Hiho_Zanzon2[i, kikan]

            if nenrei == MIN_HIHO_NENREI:
                Dattaisha_Gokei[i, kikan] = 0.
            else:
                Dattaisha_Gokei[i, kikan] = \
                    (G.Hihokensha[y1, i - 1, kikan - 1]["ninzu"]
                     - Hiho_Zanzon[i, kikan])

                if kikan == MAX_HIHO_KIKAN:
                    Dattaisha_Gokei[i, kikan] += \
                        G.Hihokensha[y1, i - 1, kikan]["ninzu"]

            # **ここは 20歳のとき配列の外を読む**（B10）。守りが無い
            Hasseisha_Shogai[i, kikan] = \
                (_c_at(G.Hihokensha, y1, i - 1, kikan - 1)["ninzu"]
                 * G.Hasseiryoku_Shogai[sotai_nendo, i])

            if kikan == MAX_HIHO_KIKAN:
                Hasseisha_Shogai[i, kikan] += \
                    (_c_at(G.Hihokensha, y1, i - 1, kikan)["ninzu"]
                     * G.Hasseiryoku_Shogai[sotai_nendo, i])

            Hihokensha_Shibou[i, kikan]["ninzu"] = \
                (_c_at(G.Hihokensha, y1, i - 1, kikan - 1)["ninzu"]
                 * G.Dattairyoku_Shibou[sotai_nendo, i])

            if kikan == MAX_HIHO_KIKAN:
                Hihokensha_Shibou[i, kikan]["ninzu"] += \
                    (_c_at(G.Hihokensha, y1, i - 1, kikan)["ninzu"]
                     * G.Dattairyoku_Shibou[sotai_nendo, i])

            Dattaisha_Seizon[i, kikan] = \
                (Dattaisha_Gokei[i, kikan]
                 - Hihokensha_Shibou[i, kikan]["ninzu"])

            G.Taikisha[sotai_nendo, i, kikan]["ninzu"] = \
                Taiki_Zanzon[i, kikan] + Dattaisha_Seizon[i, kikan]

            if ext_b:
                Shinkikanyu2[i] += \
                    (G.Hihokensha[sotai_nendo, i, kikan]["ninzu"]
                     * G.Hassei_Wariai_Rorei[sotai_nendo,
                                             nenrei - MIN_ROREI_JUKYU])

        G.Hihokensha[sotai_nendo, i, 0]["ninzu"] = \
            Shinkikanyu[i] + Saikanyu[i, 0]

        if G.Option == 1:
            if ext_b:
                Shinkikanyu2[i] += \
                    (G.Hihokensha[sotai_nendo, i, 0]["ninzu"]
                     * G.Hassei_Wariai_Rorei[sotai_nendo,
                                             nenrei - MIN_ROREI_JUKYU])

            G.Hihokensha2[sotai_nendo, i, 0]["ninzu"] = Shinkikanyu2[i]

        G.Taikisha[sotai_nendo, i, 0]["ninzu"] = Taiki_Zanzon[i, 0]

        Dattaisha_Gokei[i, 0] = 0.
        Dattaisha_Seizon[i, 0] = 0.
        Hihokensha_Shibou[i, 0]["ninzu"] = 0.
        Hasseisha_Shogai[i, 0] = 0.

    # ---- 構造体の中身を人数で加重平均する --------------------------
    #
    # **③でいちばん重いところ。** 原本は 年齢(51) × 期間(51) の二重ループで
    # 1マスあたり14回 `str_op` を呼ぶ。行ごとに数えたら、この 14行だけで
    # `str_op` の呼び出し 2,460万回のうち **約1,500万回（61%）**を占めて
    # いた。**両軸をまとめる。**
    #
    # まとめてよい理由: 読むのは**前年度** `[y1, i-1, kikan-1]` と
    # `[y1, i-1, kikan]`、書くのは**当年度** `[sotai_nendo, i, kikan]` で
    # 別のスライス。当年度から読むのは自分のマスの `ninzu` だけで、それも
    # 読んでから同じマスを上書きするので、マスをまたぐ依存が無い。原本は
    # 年齢・期間とも降順に回すが、読み書きが別年度なので順序に意味が無い。
    #
    # 各スロットに当たる演算の列（掛ける・足す）はマスごとに変わらないので
    # **ビット一致する**（`str_op.scalar_arr` の解説）。
    sh = (_HIHO_N, _KIKAN_N)

    # 前年度の被保険者。原本は
    #   年齢 == MIN_HIHO_NENREI  → ゼロ（期間を問わず）
    #   期間 == 0                → ゼロ
    #   ほか                     → `G.Hihokensha[y1, i-1, kikan-1]`
    # なので、1行1列ずらして残りをゼロで埋める
    Hiho_Zennen = np.zeros(sh, dtype=HH)
    Hiho_Zennen[1:, 1:] = G.Hihokensha[y1, :_HIHO_N - 1, :_KIKAN_N - 1]

    # 前年度の待機者。年齢 == MIN_HIHO_NENREI だけゼロ（期間はずらさない）
    Taiki_Zennen = np.zeros(sh, dtype=HH)
    Taiki_Zennen[1:, :] = G.Taikisha[y1, :_HIHO_N - 1, :]

    # 納付状況は年齢だけで決まる。`(51, 1)` にして期間の軸へ放送する
    nj_b = Noufu_Jokyo[:, None]

    # `scalar_2` に渡す係数。期間 0 だけ式が違う（新規加入がここに入る）
    c_hiho = Saikanyu * 0.5 + Hiho_Zanzon
    c_hiho[:, 0] = (Saikanyu[:, 0] + Shinkikanyu) * 0.5

    _t1 = np.empty(sh, dtype=HH)
    _t2 = np.empty(sh, dtype=HH)
    _t3 = np.empty(sh, dtype=HH)

    # ---- 被保険者 ----
    # `add(scalar(Saikanyu, Taiki_Zennen), scalar(Hiho_Zanzon, Hiho_Zennen))`
    scalar_arr(Saikanyu[:, :, None], Taiki_Zennen, _t1)
    scalar_arr(Hiho_Zanzon[:, :, None], Hiho_Zennen, _t2)
    add_arr(_t1, _t2, _t1)
    # `add(↑, scalar_2(係数, 納付状況, nendo))`
    scalar_2_arr(c_hiho[:, :, None], nj_b, nendo, _t3)
    add_arr(_t1, _t3, _t1)
    # 人数は当年度のものに差し替えてから1人あたりに直す
    _t1["ninzu"] = G.Hihokensha[sotai_nendo]["ninzu"]
    average_by_ninzu_arr(_t1, G.Hihokensha[sotai_nendo])

    # ---- 待機者 ----
    scalar_arr(Taiki_Zanzon[:, :, None], Taiki_Zennen, _t1)
    scalar_arr(Dattaisha_Seizon[:, :, None], Hiho_Zennen, _t2)
    add_arr(_t1, _t2, _t1)
    scalar_2_arr((Dattaisha_Seizon * 0.5)[:, :, None], nj_b, nendo, _t3)
    add_arr(_t1, _t3, _t1)
    _t1["ninzu"] = G.Taikisha[sotai_nendo]["ninzu"]
    average_by_ninzu_arr(_t1, G.Taikisha[sotai_nendo])

    # ---- 死亡した人（原本は `Hiho_Zennen` を書き換えて使い回す。
    #      値渡しなので元の配列は変わらない） ----
    # `scalar_2(0.5, 納付状況, nendo)` は期間に依らないので年齢ぶんだけ
    # 作り、期間の軸へ放送する。連続でないスライスを `view` に渡さない
    # よう、専用の `(51, 1)` を使う
    _t4 = np.empty((_HIHO_N, 1), dtype=HH)
    scalar_2_arr(0.5, nj_b, nendo, _t4)
    _t2[:, :] = Hiho_Zennen
    _t2["ninzu"] = Hihokensha_Shibou["ninzu"]
    add_arr(_t2, _t4, Hihokensha_Shibou)

    Taikisha_Shibou_ninzu = Taikisha_Shibou["ninzu"].copy()
    Taikisha_Shibou[:, :] = Taiki_Zennen
    Taikisha_Shibou["ninzu"] = Taikisha_Shibou_ninzu

    if G.Option == 1:
        for nenrei in range(MAX_HIHO_NENREI, MIN_HIHO_NENREI - 1, -1):
            i = nenrei - MIN_HIHO_NENREI
            nj = Noufu_Jokyo[i]
            eb = extendb(G, nendo, nenrei) == 1
            ec = extendc(G, nendo, nenrei) == 1

            for kikan in range(MAX_HIHO_KIKAN, -1, -1):
                if kikan >= 1 and nenrei >= MIN_HIHO_NENREI + 1:
                    Hiho_Zennen2 = G.Hihokensha2[y1, i - 1, kikan - 1]
                else:
                    Hiho_Zennen2 = G.Hihokensha_Zero

                Hiho_Gokei2 = scalar(Hiho_Zanzon2[i, kikan], Hiho_Zennen2)

                if kikan > 0:
                    if eb:
                        Hiho_Gokei2 = add(
                            Hiho_Gokei2,
                            scalar_2(Hiho_Zanzon2[i, kikan], nj, nendo))
                    elif ec:
                        Hiho_Gokei2 = add(
                            Hiho_Gokei2,
                            scalar_2(Hiho_Zanzon2[i, kikan] * 0.5,
                                     nj, nendo))

                Hiho_Gokei2["ninzu"] = \
                    G.Hihokensha2[sotai_nendo, i, kikan]["ninzu"]
                G.Hihokensha2[sotai_nendo, i, kikan] = \
                    average_by_ninzu(Hiho_Gokei2)

    # ---- 障害（20歳前）の新規発生 ----------------------------------
    for nenrei in range(MIN_SHOGAI_JUKYU, MAX_SHOGAI_JUKYU + 1):
        for tokyu in range(1, 2 + 1):
            Shogai_20mae_Shinki[nenrei - MIN_SHOGAI_JUKYU, tokyu] = \
                G.Shogai_Zero

    if ((shubetu == 2 or shubetu == 5)
            and (G.Kako_Saimu == 0 or nendo <= G.Kugiri_Nendo)):
        for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
            # 原本は添字が `nenrei - MIN_SHOGAI_JUKYU`（= nenrei - 20）
            s = nenrei - MIN_SHOGAI_JUKYU
            i = nenrei - MIN_HIHO_NENREI
            jinko = _sotowaku4(G, shubetu, nendo, nenrei)
            for tokyu in range(1, 2 + 1):
                rec = Shogai_20mae_Shinki[s, tokyu]
                rec["ninzu"] = (jinko
                                * G.Hassei_Wariai_20mae[sotai_nendo, i]
                                * G.Tokyu_Wariai_20mae[sotai_nendo, tokyu])

                rec["kihon"] = (rec["ninzu"]
                                * G.Full_Pension[sotai_nendo, nenrei]
                                * G.Shogai_Bairitu[tokyu])

    # ---- 障害（一般）の新規発生 ------------------------------------
    for nenrei in range(MIN_SHOGAI_JUKYU, MAX_SHOGAI_JUKYU + 1):
        for tokyu in range(1, 2 + 1):
            Shogai_Ippan_Shinki[nenrei - MIN_SHOGAI_JUKYU, tokyu] = \
                G.Shogai_Zero

    if G.Kako_Saimu == 0 or nendo <= G.Kugiri_Nendo:
        for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
            s = nenrei - MIN_SHOGAI_JUKYU
            i = nenrei - MIN_HIHO_NENREI
            for tokyu in range(1, 2 + 1):
                rec = Shogai_Ippan_Shinki[s, tokyu]
                if nenrei < 60:
                    for kikan in range(0, MAX_HIHO_KIKAN + 1):
                        rec["ninzu"] += (
                            Hasseisha_Shogai[i, kikan]
                            * G.Tokyu_Wariai_Ippan[sotai_nendo, tokyu])

                if nenrei >= 60 and (shubetu == 2 or shubetu == 5):
                    rec["ninzu"] = (
                        (_sotowaku4(G, shubetu, nendo, nenrei)
                         - G.Sotowaku_2gou[seibetu,
                                           nendo - 1 - SOTOWAKU_SHONENDO,
                                           nenrei - 1 - MIN_WAKU_NENREI])
                        * G.Hasseiryoku_Shogai[sotai_nendo, i]
                        * G.Tokyu_Wariai_Ippan[sotai_nendo, tokyu])

                rec["kihon"] = (rec["ninzu"]
                                * G.Full_Pension[sotai_nendo, nenrei]
                                * G.Shogai_Bairitu[tokyu])

    # ---- 遺族の新規発生 --------------------------------------------
    for n in range(Izoku_Tuma_Shinki.shape[0]):
        Izoku_Tuma_Shinki[n] = G.Izoku_Zero
    for n in range(Izoku_Otto_Shinki.shape[0]):
        Izoku_Otto_Shinki[n] = G.Izoku_Zero
    for n in range(Izoku_Ko_Shinki.shape[0]):
        Izoku_Ko_Shinki[n] = G.Izoku_Zero

    if shubetu == 2 and (G.Kako_Saimu == 0 or nendo <= G.Kugiri_Nendo):
        _izoku(G, nendo, shubetu, seibetu, yq,
               Hihokensha_Shibou, Izoku_Tuma_Shinki,
               G.Sokan_Tuma, G.Hassei_Wariai_Tuma,
               MIN_IZOKU_TUMA_JUKYU, MAX_IZOKU_TUMA_JUKYU, True)
        _izoku(G, nendo, shubetu, seibetu, yq,
               Hihokensha_Shibou, Izoku_Ko_Shinki,
               G.Sokan_Ko, G.Hassei_Wariai_Ko,
               MIN_IZOKU_KO_JUKYU, MAX_IZOKU_KO_JUKYU, True)

    if ((shubetu == 5 or shubetu == 6)
            and (G.Kako_Saimu == 0 or nendo <= G.Kugiri_Nendo)):
        _izoku(G, nendo, shubetu, seibetu, yq,
               Hihokensha_Shibou, Izoku_Otto_Shinki,
               G.Sokan_Otto, G.Hassei_Wariai_Otto,
               MIN_IZOKU_OTTO_JUKYU, MAX_IZOKU_OTTO_JUKYU, shubetu == 5)

    # ---- 寡婦の新規発生 --------------------------------------------
    for n in range(Kafu_Shinki.shape[0]):
        Kafu_Shinki[n] = G.Kafu_Zero

    if shubetu == 2 and (G.Kako_Saimu == 0 or nendo <= G.Kugiri_Nendo):
        _kafu(G, nendo, sotai_nendo, Hihokensha_Shibou, Taikisha_Shibou,
              Kafu_Shinki)

    # ---- 死亡一時金 ------------------------------------------------
    if ((shubetu == 2 or shubetu == 5)
            and (G.Kako_Saimu == 0 or nendo <= G.Kugiri_Nendo)):
        for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
            i = nenrei - MIN_HIHO_NENREI
            for kikan in range(0, MAX_HIHO_KIKAN + 1):
                for src in (Hihokensha_Shibou, Taikisha_Shibou):
                    rec = src[i, kikan]
                    Noufu_Kikan = rec["noufu"]
                    for dankai in range(1, MENJO_DANKAI):
                        for kokko in range(1, KOKKO_HIKIAGE - 1 + 1):
                            Noufu_Kikan += (rec["menjo"][dankai, kokko]
                                            * G.Hokenryou_Wariai[dankai])

                    if Noufu_Jokyo[i]["fuka"] == 0.:
                        Noufu_Kikan_Fuka = 0.
                    else:
                        Noufu_Kikan_Fuka = (rec["fuka"]
                                            / Noufu_Jokyo[i]["fuka"])

                    if Noufu_Kikan >= 3.:
                        ic = G.Ichijikin_Nendomatu[sotai_nendo, i]
                        ic["ninzu"] += (
                            rec["ninzu"]
                            * G.Hassei_Wariai_Shibou[sotai_nendo, i])

                        ic["kyufu"] += (
                            G.Tanka_Shibou[
                                sotai_nendo,
                                Shibou_Kubun(G, nendo, Noufu_Kikan,
                                             G.Option)]
                            * rec["ninzu"]
                            * G.Hassei_Wariai_Shibou[sotai_nendo, i])

                        if Noufu_Kikan_Fuka >= 3.:
                            ic["kyufu_fuka"] += (
                                G.Tanka_Shibou_Fuka
                                * rec["ninzu"]
                                * G.Hassei_Wariai_Shibou[sotai_nendo, i]
                                * Noufu_Jokyo[i]["fuka"])

    # ---- 老齢基礎の新規裁定 ----------------------------------------
    for jukyu_nenrei in range(MIN_ROREI_JUKYU, 70 + 1):
        Rorei_Shinki[jukyu_nenrei - MIN_ROREI_JUKYU] = G.Rorei_Zero
        if G.Option == 1:
            G.Rorei_Shinki2[jukyu_nenrei - MIN_ROREI_JUKYU] = G.Rorei_Zero

    if (G.Kako_Saimu == 0 or G.Jyukyusha_Nomi == 0
            or nendo <= G.Kugiri_Nendo):
        _rorei_shinki(G, nendo, sotai_nendo, shubetu, seibetu, Rorei_Shinki)

    # ---- 老齢基礎の年度末（前年度 × (1 - 失権率) × 改定率 ＋ 新規） --
    # 原本は `jukyu_nenrei`（11通り）× `nenrei`（55通り）× 5配列の
    # 三重ループで、1年度・1種別あたり 3,025回 `adjustbenefit(scalar())`
    # を呼ぶ。**年齢と受給年齢の両軸をまとめる。**
    #
    # まとめてよい理由: 読むのは**前年度** `[y-1, n-1, j]`、書くのは
    # **当年度** `[y, n, j]` で、別のスライスなので依存が無い。原本は
    # `nenrei` を降順に回すが、読み書きが別年度なので順序に意味が無い。
    # 各スロットに当たる演算は `zan` を掛けて `kt` を掛ける2回だけで
    # 変わらないので**ビット一致する**（`str_op.scalar_arr` の解説）。
    #
    # `zan` と `kt` は `nenrei` だけで決まるので、年齢の軸に沿った
    # 55本のベクトルにして放送する。
    n_lo = 1                                    # nenrei = 61
    n_hi = MAX_ROREI_JUKYU - MIN_ROREI_JUKYU     # nenrei = 115 → n = 55
    nenreis = np.arange(MIN_ROREI_JUKYU + n_lo, MAX_ROREI_JUKYU + 1)
    kt_v = G.kaiteiritu_tannen[nendo - ECON_SHONENDO,
                               nenreis][:, None, None]
    zan_v = (1. - G.Shikkenritu_Rorei[
        sotai_nendo, nenreis - MIN_HIHO_NENREI])[:, None, None]

    for name in ("Rorei_Nendomatu", "Rorei_Kyu_Nendomatu",
                 "Turo_Kyu_Nendomatu", "Gonen_Nendomatu",
                 "Rorei_Ichibu_Nendomatu"):
        a = getattr(G, name)
        src = a[sotai_nendo - 1, n_lo - 1:n_hi]
        dst = a[sotai_nendo, n_lo:n_hi + 1]
        # `adjustbenefit(kt, scalar(zan, src))` の2段を、同じ順で当てる。
        # 素通しの欄（人数・付加年金）を `adjustbenefit` が写し戻すので
        # `dst` を入力にした in-place にはできない（写し戻す前に
        # 上書きしてしまう）。1年度ぶんの控えを1枚使う
        tmp = np.empty(dst.shape, dtype=a.dtype)
        scalar_arr(zan_v, src, tmp)
        adjustbenefit_arr(kt_v, tmp, dst)

    # 65歳の一部繰上げの拡大（生年度で決まる5コホートだけ）。
    # `nenrei == 65` の1本だけなので受給年齢の軸をまとめる
    seinendo = nendo - 65
    if SUIKEISHONENDO - 64 <= seinendo <= SUIKEISHONENDO - 60:
        n65 = 65 - MIN_ROREI_JUKYU
        row = G.Rorei_Ichibu_Nendomatu[sotai_nendo, n65]
        multiply_arr(
            row,
            G.Kakudai_Ichibu[
                seinendo - (SUIKEISHONENDO - MAX_ROREI_JUKYU)],
            row)

    # `nenrei == jukyu_nenrei` の対角だけに新規裁定を足す。
    # `n = nenrei - 60`・`j = jukyu_nenrei - 60` なので **n == j**。
    # `n` は 1 以上なので j = 1..10（j = 0 は下の `n = 0` の代入が持つ）
    for j in range(n_lo, 70 - MIN_ROREI_JUKYU + 1):
        G.Rorei_Nendomatu[sotai_nendo, j, j] = add(
            G.Rorei_Nendomatu[sotai_nendo, j, j], Rorei_Shinki[j])

    if G.Option == 1:
        # 65歳・受給65歳の1マスだけ。人数だけ 0 にしてから足す
        # （年金額は足す）。`Rorei_Shinki2` を書き換える副作用も原本のまま
        j65 = 65 - MIN_ROREI_JUKYU
        n65 = 65 - MIN_ROREI_JUKYU
        G.Rorei_Shinki2[j65]["ninzu"] = 0.
        G.Rorei_Nendomatu[sotai_nendo, n65, j65] = add(
            G.Rorei_Nendomatu[sotai_nendo, n65, j65], G.Rorei_Shinki2[j65])

    # ---- `n = 0`（60歳）の代入。上のまとめは n = 1..55 しか書かない ----
    for jukyu_nenrei in range(MIN_ROREI_JUKYU, 70 + 1):
        j = jukyu_nenrei - MIN_ROREI_JUKYU
        if jukyu_nenrei == MIN_ROREI_JUKYU:
            G.Rorei_Nendomatu[sotai_nendo, 0, j] = Rorei_Shinki[j]
        else:
            G.Rorei_Nendomatu[sotai_nendo, 0, j] = G.Rorei_Zero

        G.Rorei_Kyu_Nendomatu[sotai_nendo, 0, j] = G.Rorei_Kyu_Zero
        G.Turo_Kyu_Nendomatu[sotai_nendo, 0, j] = G.Rorei_Kyu_Zero
        G.Gonen_Nendomatu[sotai_nendo, 0, j] = G.Gonen_Zero

    # 原本は `[0][0]` を `jukyu_nenrei` ごとに毎回 0 にする（同じ代入を
    # 11回するだけなので1回で同じ）
    G.Rorei_Ichibu_Nendomatu[sotai_nendo, 0, 0] = G.Rorei_Zero

    # ---- 45年化のときの年度末調整（**前年度**を書き換える） --------
    if G.Option == 1:
        if (G.OPTION_START <= nendo
                <= G.OPTION_START + G.OP_HIKIAGE_KANKAKU * 4):
            for tokyu in range(1, 2 + 1):
                for nenrei in range(MAX_SHOGAI_JUKYU, MIN_SHOGAI_JUKYU, -1):
                    k = Nendomatu_Tyousei_Keisu(G, nendo, nenrei)
                    n = nenrei - 1 - MIN_SHOGAI_JUKYU
                    G.Shogai_Ippan_Nendomatu[
                        sotai_nendo - 1, n, tokyu]["kihon"] *= k
                    G.Shogai_20mae_Nendomatu[
                        sotai_nendo - 1, n, tokyu]["kihon"] *= k

            for name, lo, hi in (
                    ("Izoku_Tuma_Nendomatu", MIN_IZOKU_TUMA_JUKYU,
                     MAX_IZOKU_TUMA_JUKYU),
                    ("Izoku_Otto_Nendomatu", MIN_IZOKU_OTTO_JUKYU,
                     MAX_IZOKU_OTTO_JUKYU),
                    ("Izoku_Ko_Nendomatu", MIN_IZOKU_KO_JUKYU,
                     MAX_IZOKU_KO_JUKYU)):
                a = getattr(G, name)
                for nenrei in range(hi, lo, -1):
                    a[sotai_nendo - 1, nenrei - 1 - lo]["kihon"] *= \
                        Nendomatu_Tyousei_Keisu(G, nendo, nenrei)

    # ---- 障害の年度末 ----------------------------------------------
    #
    # 原本は 等級(2) × 年齢(95) × 3配列 の二重ループ。読むのは前年度
    # `[y-1, n-1, t]` と自分のマス、書くのは当年度 `[y, n, t]` なので
    # 両軸をまとめる（`str_op.scalar_arr` の解説）。等級は 1・2 だけ使う
    # （添字 0 は使わない）のでスライスは連続でないが、view は itemsize が
    # 変わらないので通る（1個ずつ版と配列全体で一致することを実測した）。
    NS = MAX_SHOGAI_JUKYU - MIN_SHOGAI_JUKYU + 1             # 96
    T = slice(1, SHOGAI_TOKYU)                               # 等級 1・2
    nenreis = np.arange(MIN_SHOGAI_JUKYU + 1, MAX_SHOGAI_JUKYU + 1)
    kt_v = G.kaiteiritu_tannen[nendo - ECON_SHONENDO, nenreis][:, None, None]
    zan_ip = (1. - G.Shikkenritu_Ippan[sotai_nendo, 1:NS])[:, None, None]
    zan_20 = (1. - G.Shikkenritu_20mae[sotai_nendo, 1:NS])[:, None, None]
    _s1 = np.empty((NS - 1, SHOGAI_TOKYU - 1), dtype=SD)
    _s2 = np.empty((NS - 1, SHOGAI_TOKYU - 1), dtype=SD)
    A_ip = G.Shogai_Ippan_Nendomatu
    A_20 = G.Shogai_20mae_Nendomatu
    A_ky = G.Shogai_Kyu_Nendomatu

    # `add(adjustbenefit(kt, scalar(1 - 失権率, 前年度)), 新規)` の3段を
    # 同じ順で当てる。`adjustbenefit` は素通しの欄を写し戻すので
    # in-place にできず、控えを2枚使う
    scalar_arr(zan_ip, A_ip[sotai_nendo - 1, :NS - 1, T], _s1)
    adjustbenefit_arr(kt_v, _s1, _s2)
    add_arr(_s2, Shogai_Ippan_Shinki[1:NS, T], A_ip[sotai_nendo, 1:NS, T])

    scalar_arr(zan_20, A_20[sotai_nendo - 1, :NS - 1, T], _s1)
    adjustbenefit_arr(kt_v, _s1, _s2)
    add_arr(_s2, Shogai_20mae_Shinki[1:NS, T], A_20[sotai_nendo, 1:NS, T])

    # 旧法は**一般の失権率**を使う（原本のとおり）。新規は足さない
    scalar_arr(zan_ip, A_ky[sotai_nendo - 1, :NS - 1, T], _s1)
    adjustbenefit_arr(kt_v, _s1, A_ky[sotai_nendo, 1:NS, T])

    # 加給は 人数 × (単価12歳未満 × 割合 + 単価3歳以降 × 割合)。要素ごとで
    # 掛ける順・足す順は原本のまま。年齢で決まる量は (95, 1) で等級へ放送
    # する。`cur_*` は view なので欄への代入が元に伝わる
    k12 = G.Kakyu_Tanka_12shi[sotai_nendo, nenreis][:, None]
    k3 = G.Kakyu_Tanka_3shiiko[sotai_nendo, nenreis][:, None]
    w_ip = (k12 * G.Kakyu_Wariai_Ippan_12shi[sotai_nendo, 1:NS][:, None]
            + k3 * G.Kakyu_Wariai_Ippan_3shiiko[sotai_nendo, 1:NS][:, None])
    w_20 = (k12 * G.Kakyu_Wariai_20mae_12shi[sotai_nendo, 1:NS][:, None]
            + k3 * G.Kakyu_Wariai_20mae_3shiiko[sotai_nendo, 1:NS][:, None])
    cur_ip = A_ip[sotai_nendo, 1:NS, T]
    cur_20 = A_20[sotai_nendo, 1:NS, T]
    cur_ky = A_ky[sotai_nendo, 1:NS, T]
    cur_ip["kakyu"] = cur_ip["ninzu"] * w_ip
    cur_20["kakyu"] = cur_20["ninzu"] * w_20

    # 旧法の加算は**一般の加算割合**を使う（原本のとおり）。原本の
    # `min(Temp, kakyu)` は Python の `min` で、`kakyu` が**厳密に**小さい
    # ときだけ `kakyu`、等しい・NaN のときは `Temp` を返す。`np.minimum`
    # は NaN と ±0 の扱いが違うので、`np.where` で同じ規則にする
    temp_ky = cur_ky["ninzu"] * w_ip
    kk = cur_ky["kakyu"]
    cur_ky["kakyu"] = np.where(kk < temp_ky, kk, temp_ky)

    # 免除の加算は前年度の加算に対する比で按分。前年度の加算が 0 なら 0。
    # `(kakyu * zen.menjo_kakyu) / zen.kakyu` の順は原本のまま。0 割りは
    # マスクで捨てるので警告だけ黙らせる
    zen = A_ky[sotai_nendo - 1, :NS - 1, T]
    zk = zen["kakyu"]
    with np.errstate(divide="ignore", invalid="ignore"):
        mk = cur_ky["kakyu"] * zen["menjo_kakyu"] / zk
    cur_ky["menjo_kakyu"] = np.where(zk == 0., 0., mk)

    # ---- `n = 0`（20歳）の代入。上のまとめは n = 1..95 しか書かない ----
    for tokyu in range(1, 2 + 1):
        G.Shogai_Ippan_Nendomatu[sotai_nendo, 0, tokyu] = \
            Shogai_Ippan_Shinki[0, tokyu]
        G.Shogai_20mae_Nendomatu[sotai_nendo, 0, tokyu] = \
            Shogai_20mae_Shinki[0, tokyu]
        G.Shogai_Kyu_Nendomatu[sotai_nendo, 0, tokyu] = G.Shogai_Zero

        k12 = G.Kakyu_Tanka_12shi[sotai_nendo, MIN_SHOGAI_JUKYU]
        k3 = G.Kakyu_Tanka_3shiiko[sotai_nendo, MIN_SHOGAI_JUKYU]

        G.Shogai_Ippan_Nendomatu[sotai_nendo, 0, tokyu]["kakyu"] = (
            Shogai_Ippan_Shinki[0, tokyu]["ninzu"]
            * (k12 * G.Kakyu_Wariai_Ippan_12shi[sotai_nendo, 0]
               + k3 * G.Kakyu_Wariai_Ippan_3shiiko[sotai_nendo, 0]))

        G.Shogai_20mae_Nendomatu[sotai_nendo, 0, tokyu]["kakyu"] = (
            Shogai_20mae_Shinki[0, tokyu]["ninzu"]
            * (k12 * G.Kakyu_Wariai_20mae_12shi[sotai_nendo, 0]
               + k3 * G.Kakyu_Wariai_20mae_3shiiko[sotai_nendo, 0]))

    # ---- 遺族の年度末 ----------------------------------------------
    _izoku_nendomatu(G, nendo, sotai_nendo, "Izoku_Tuma_Nendomatu",
                     G.Shikkenritu_Tuma, Izoku_Tuma_Shinki,
                     G.Kakyu_Wariai_Tuma_12shi, G.Kakyu_Wariai_Tuma_3shiiko,
                     MIN_IZOKU_TUMA_JUKYU, MAX_IZOKU_TUMA_JUKYU)
    _izoku_nendomatu(G, nendo, sotai_nendo, "Izoku_Otto_Nendomatu",
                     G.Shikkenritu_Otto, Izoku_Otto_Shinki,
                     G.Kakyu_Wariai_Otto_12shi, G.Kakyu_Wariai_Otto_3shiiko,
                     MIN_IZOKU_OTTO_JUKYU, MAX_IZOKU_OTTO_JUKYU)
    _izoku_nendomatu(G, nendo, sotai_nendo, "Izoku_Ko_Nendomatu",
                     G.Shikkenritu_Ko, Izoku_Ko_Shinki,
                     G.Kakyu_Wariai_Ko_12shi, G.Kakyu_Wariai_Ko_3shiiko,
                     MIN_IZOKU_KO_JUKYU, MAX_IZOKU_KO_JUKYU)

    # ---- 寡婦の年度末（改定率は 67歳未満のものを使う） --------------
    # 読むのは前年度 `[y-1, n-1]`、書くのは当年度 `[y, n]` なので年齢の
    # 軸をまとめる（`str_op.scalar_arr` の解説）。原本は降順に回すが、
    # 読み書きが別年度なので順序に意味が無い。`adjustbenefit` は素通しの
    # 欄を写し戻すので in-place にできず、控えを2枚使う
    kt67 = G.kaiteiritu_tannen[nendo - ECON_SHONENDO, UNDER_67]
    NK = MAX_KAFU_JUKYU - MIN_KAFU_JUKYU + 1                 # 39
    zan_v = (1. - G.Shikkenritu_Kafu[sotai_nendo, 1:NK])[:, None]
    _k1 = np.empty(NK - 1, dtype=KD)
    _k2 = np.empty(NK - 1, dtype=KD)

    scalar_arr(zan_v, G.Kafu_Nendomatu[sotai_nendo - 1, :NK - 1], _k1)
    adjustbenefit_arr(kt67, _k1, _k2)
    add_arr(_k2, Kafu_Shinki[1:NK], G.Kafu_Nendomatu[sotai_nendo, 1:NK])

    scalar_arr(zan_v, G.Kafu_Kyu_Nendomatu[sotai_nendo - 1, :NK - 1], _k1)
    adjustbenefit_arr(kt67, _k1, G.Kafu_Kyu_Nendomatu[sotai_nendo, 1:NK])

    G.Kafu_Nendomatu[sotai_nendo, 0] = Kafu_Shinki[0]
    G.Kafu_Kyu_Nendomatu[sotai_nendo, 0] = G.Kafu_Zero

    return


def _sotowaku4(G, shubetu, nendo, nenrei):
    """外枠の4点平均（原本が3か所で同じ形に書いているもの）。

    ```c
    ( Sotowaku[shubetu - 1][nendo - 1][nenrei - 2]
      + Sotowaku[shubetu - 1][nendo - 1][nenrei - 1]
      + Sotowaku[shubetu - 1][nendo    ][nenrei - 1]
      + Sotowaku[shubetu - 1][nendo    ][nenrei    ] ) / 4.
    ```

    **`shubetu - 1`** を読むのは、第1号（2・5）の1つ前が
    「人口」（`SOTOWAKU_JINKO` = 1・4）だから。
    """
    a = G.Sotowaku
    y = nendo - SOTOWAKU_SHONENDO
    x = nenrei - MIN_WAKU_NENREI
    return (a[shubetu - 1, y - 1, x - 2]
            + a[shubetu - 1, y - 1, x - 1]
            + a[shubetu - 1, y, x - 1]
            + a[shubetu - 1, y, x]) / 4.


def _bunpu(sokan_row, i, lo, hi):
    """相関（平均年齢差）から受給年齢の分布を作る。

    ```c
    if( n == (int)Sokan[…] )          Bunpu[n] = Sokan[…] - n;
    else if( n == (int)Sokan[…] + 1 ) Bunpu[n] = n - Sokan[…];
    else                              Bunpu[n] = 1.;
    ```

    使われるのは `1. - Bunpu[n]` なので、**相関のすぐ上下の2歳だけが
    0 でなく、ほかは 0** になる（線形補間）。
    """
    s = sokan_row[i]
    k = int(s)
    b = np.ones(hi - lo + 1)
    if lo <= k <= hi:
        b[k - lo] = s - k
    if lo <= k + 1 <= hi:
        b[k + 1 - lo] = (k + 1) - s
    return b


def _izoku(G, nendo, shubetu, seibetu, yq, Hihokensha_Shibou, Shinki,
           Sokan, Hassei, lo, hi, do_60_64):
    """遺族（妻・夫・子）の新規発生。受給年齢の軸はまとめて計算する。

    60〜64歳の枝で読む生命表の性別の添字が1つずれている（B11）ので
    `_c_at()` を通す。`do_60_64` は原本の
    `( nenrei >= 60 && nenrei <= 64 ) && shubetu == 5` の形を写した
    もので、種別 6 では 60〜64歳の枝を通らない。
    """
    sotai_nendo = nendo - SHONENDO
    for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
        i = nenrei - MIN_HIHO_NENREI
        b = _bunpu(Sokan[sotai_nendo], i, lo, hi)
        w = 1. - b
        fp = G.Full_Pension[sotai_nendo, nenrei]
        h = Hassei[sotai_nendo, i]

        if nenrei < 60:
            for kikan in range(0, MAX_HIHO_KIKAN + 1):
                t = Hihokensha_Shibou[i, kikan]["ninzu"] * h * w
                Shinki["ninzu"] += t
                Shinki["kihon"] += t * fp

        if 60 <= nenrei <= 64 and do_60_64:
            t = ((_sotowaku4(G, shubetu, nendo, nenrei)
                  - G.Sotowaku_2gou[seibetu,
                                    nendo - 1 - SOTOWAKU_SHONENDO,
                                    nenrei - 1 - MIN_WAKU_NENREI])
                 * _c_at(G.q, yq, nenrei, seibetu)
                 * h * w)
            Shinki["ninzu"] += t
            Shinki["kihon"] += t * fp


def _kafu(G, nendo, sotai_nendo, Hihokensha_Shibou, Taikisha_Shibou,
          Kafu_Shinki):
    """寡婦年金の新規発生（種別 2 だけ）。受給年齢の軸はまとめて計算。

    納付月数が **10年以上**（`Noufu_Kikan >= 10.`）のときだけ出る。
    `Noufu_Kikan` は納付＋学生＋若年者猶予＋免除（段階別・国庫別）の
    素の合計で、保険料割合を掛けない（死亡一時金の判定とは別の式）。
    """
    for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
        i = nenrei - MIN_HIHO_NENREI
        seinendo = nendo - nenrei
        b = _bunpu(G.Sokan_Kafu[sotai_nendo], i, MIN_KAFU_JUKYU,
                   MAX_KAFU_JUKYU)
        w = 1. - b
        fp = G.Full_Pension[sotai_nendo, nenrei]
        h = G.Hassei_Wariai_Kafu[sotai_nendo, i]
        kn = G.Kanou_Nensu[nendo - SHONENDO, seinendo - N_O_NENDO]

        for kikan in range(0, MAX_HIHO_KIKAN + 1):
            for src in (Hihokensha_Shibou, Taikisha_Shibou):
                rec = src[i, kikan]
                Noufu_Kikan = (rec["noufu"] + rec["gakusei"]
                               + rec["wakamono"])
                for dankai in range(1, MENJO_DANKAI):
                    for kokko in range(1, KOKKO_HIKIAGE - 1 + 1):
                        Noufu_Kikan += rec["menjo"][dankai, kokko]

                if Noufu_Kikan >= 10.:
                    base = rec["ninzu"] * h * w
                    Kafu_Shinki["ninzu"] += base

                    Kafu_Shinki["noufu"] += (
                        3. / 4. * fp * rec["noufu"] / kn
                        * rec["ninzu"] * h * w)

                    for dankai in range(1, MENJO_DANKAI):
                        for kokko in range(1, KOKKO_HIKIAGE - 1 + 1):
                            mj = rec["menjo"][dankai, kokko]
                            Kafu_Shinki["noufu"] += (
                                3. / 4. * G.Hokenryou_Wariai[dankai] * fp
                                * mj / kn * rec["ninzu"] * h * w)

                            Kafu_Shinki["menjo"][:, dankai, kokko] += (
                                3. / 4. * G.Kokko_Wariai[kokko]
                                * (1. - G.Hokenryou_Wariai[dankai]) * fp
                                * mj / kn * rec["ninzu"] * h * w)


def _rorei_shinki(G, nendo, sotai_nendo, shubetu, seibetu, Rorei_Shinki):
    """老齢基礎の新規裁定（待期者から）。`siml.c:1010-1170` の忠実移植。

    `Taikisha[…].ninzu *= ( 1. - 受給発生割合 )` で**その場で減らす**
    ので、受給年齢（= 年齢）のループを回すたびに待期者が減る。
    """
    for nenrei in range(MIN_ROREI_JUKYU, 70 + 1):
        jukyu_nenrei = nenrei
        j = jukyu_nenrei - MIN_ROREI_JUKYU
        seinendo = nendo - nenrei
        i = nenrei - MIN_HIHO_NENREI
        rec = Rorei_Shinki[j]

        fp = G.Full_Pension[sotai_nendo, nenrei]
        kr = G.Kyufu_ritu[j, seinendo - (SUIKEISHONENDO - 70), seibetu - 1]
        kn = G.Kanou_Nensu[nendo - SHONENDO, seinendo - N_O_NENDO]
        hw = G.Hassei_Wariai_Rorei[sotai_nendo, j]
        eb = (G.Option == 1 and extendb(G, nendo, nenrei) == 1)

        for kikan in range(0, MAX_HIHO_KIKAN + 1):
            t = G.Taikisha[sotai_nendo, i, kikan]

            rec["ninzu"] += t["ninzu"] * hw

            rec["noufu"] += (fp * kr * t["noufu"] / kn * t["ninzu"] * hw)

            for dankai in range(ZENGAKU, MENJO_1_4 + 1):
                for kokko in range(1, KOKKO_HIKIAGE - 1 + 1):
                    mj = t["menjo"][dankai, kokko]
                    rec["noufu"] += (fp * kr * G.Hokenryou_Wariai[dankai]
                                     * mj / kn * t["ninzu"] * hw)

                    rec["menjo"][dankai, kokko] += (
                        fp * kr * G.Kokko_Wariai[kokko]
                        * (1. - G.Hokenryou_Wariai[dankai])
                        * mj / kn * t["ninzu"] * hw)

            rec["fuka"] += (G.Full_Pension_Fuka * kr * t["fuka"]
                            * t["ninzu"] * hw)

            t["ninzu"] *= (1. - hw)

            if G.Option == 1:
                if eb:
                    h = G.Hihokensha[sotai_nendo, i, kikan]

                    rec["ninzu"] += h["ninzu"] * hw
                    rec["noufu"] += (fp * kr * h["noufu"] / kn
                                     * h["ninzu"] * hw)

                    for dankai in range(ZENGAKU, MENJO_1_4 + 1):
                        for kokko in range(1, KOKKO_HIKIAGE - 1 + 1):
                            mj = h["menjo"][dankai, kokko]
                            rec["noufu"] += (
                                fp * kr * G.Hokenryou_Wariai[dankai]
                                * mj / kn * h["ninzu"] * hw)

                            rec["menjo"][dankai, kokko] += (
                                fp * kr * G.Kokko_Wariai[kokko]
                                * (1. - G.Hokenryou_Wariai[dankai])
                                * mj / kn * h["ninzu"] * hw)

                    rec["fuka"] += (G.Full_Pension_Fuka * kr * h["fuka"]
                                    * h["ninzu"] * hw)

                    h["ninzu"] *= (1. - hw)

                if nenrei == 65:
                    # 延長ぶんは 65歳でまとめて裁定する（発生割合を
                    # 掛けない）
                    h2 = G.Hihokensha2[sotai_nendo, i, kikan]
                    r2 = G.Rorei_Shinki2[j]

                    r2["ninzu"] += h2["ninzu"]
                    r2["noufu"] += (fp * kr * h2["noufu"] / kn
                                    * h2["ninzu"])

                    for dankai in range(ZENGAKU, MENJO_1_4 + 1):
                        for kokko in range(1, KOKKO_HIKIAGE - 1 + 1):
                            mj = h2["menjo"][dankai, kokko]
                            r2["noufu"] += (
                                fp * kr * G.Hokenryou_Wariai[dankai]
                                * mj / kn * h2["ninzu"])

                            r2["menjo"][dankai, kokko] += (
                                fp * kr * G.Kokko_Wariai[kokko]
                                * (1. - G.Hokenryou_Wariai[dankai])
                                * mj / kn * h2["ninzu"])

                    r2["fuka"] += (G.Full_Pension_Fuka * kr * h2["fuka"]
                                   * h2["ninzu"])

                    h2["ninzu"] = 0.


def _izoku_nendomatu(G, nendo, sotai_nendo, name, Shikken, Shinki,
                     K12, K3, lo, hi):
    """遺族の年度末（3つとも同じ形）。`siml.c:1367-1450` の忠実移植。"""
    a = getattr(G, name)
    kt_row = G.kaiteiritu_tannen[nendo - ECON_SHONENDO]
    N = hi - lo + 1                     # n = 0..N-1 ↔ nenrei = lo..hi

    # 読むのは前年度 `[y-1, n-1]`、書くのは当年度 `[y, n]` なので年齢の
    # 軸をまとめる（`str_op.scalar_arr` の解説）。n = 1..N-1 を一度に。
    # 改定率と失権率は年齢で決まるので、年齢の軸に沿ったベクトルで放送する
    zan_v = (1. - Shikken[sotai_nendo, 1:N])[:, None]
    kt_v = kt_row[lo + 1:hi + 1][:, None]
    _i1 = np.empty(N - 1, dtype=a.dtype)
    _i2 = np.empty(N - 1, dtype=a.dtype)
    scalar_arr(zan_v, a[sotai_nendo - 1, :N - 1], _i1)
    adjustbenefit_arr(kt_v, _i1, _i2)
    add_arr(_i2, Shinki[1:N], a[sotai_nendo, 1:N])

    # 加給は人数 × (単価12歳未満 × 割合 + 単価3歳以降 × 割合)。要素ごとで
    # 掛ける順・足す順は原本のまま。`cur` は view なので欄への代入が伝わる
    cur = a[sotai_nendo, 1:N]
    cur["kakyu"] = (
        cur["ninzu"]
        * (G.Kakyu_Tanka_12shi[sotai_nendo, lo + 1:hi + 1]
           * K12[sotai_nendo, 1:N]
           + G.Kakyu_Tanka_3shiiko[sotai_nendo, lo + 1:hi + 1]
           * K3[sotai_nendo, 1:N]))

    a[sotai_nendo, 0] = Shinki[0]
    a[sotai_nendo, 0]["kakyu"] = (
        Shinki[0]["ninzu"]
        * (G.Kakyu_Tanka_12shi[sotai_nendo, lo] * K12[sotai_nendo, 0]
           + G.Kakyu_Tanka_3shiiko[sotai_nendo, lo] * K3[sotai_nendo, 0]))
