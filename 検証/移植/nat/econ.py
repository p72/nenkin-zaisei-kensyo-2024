# -*- coding: utf-8 -*-
"""
国民年金/econ.c の忠実移植（経済前提を当てはめて年金額を作る）
===============================================================
532 行。経済前提（物価上昇率と実質賃金上昇率）を読んで、
**単年度の改定率**と**累積の改定率**を作り、基礎年金の満額と
加給の単価を年度別・年齢別に出す。

    kaiteiritu_tannen[年度][年齢]   単年度の改定率（グローバル）
    kaiteiritu_ruiseki[年度][年齢]  累積の改定率（`econ()` の局所）
    Full_Pension[年度][年齢]        基礎年金の満額
    Kakyu_Tanka_12shi / _3shiiko    加給の単価
    Tanka_Shibou[年度][区分]        死亡一時金の単価

年齢別の改定率 — 67歳が境目
---------------------------
```c
if( nenrei == UNDER_67 ) { …賃金と物価を見比べる… }
else                     { …別の見比べ方… }
```

`UNDER_67` は 67。**新規裁定（67歳以下）は賃金、既裁定（68歳以上）は
物価**でスライドするのが本則。`kaiteiritu_make_before` が
2021年度（`TINSURA_KAISHI`）より前の規則、`kaiteiritu_make` が
2021年度以降の規則。

```c
if( TINSURA == 1 ){
  if( nendo < TINSURA_NENDO ) kaiteiritu_make_before(…);
  else                        kaiteiritu_make(…);
} else {
  kaiteiritu_make_before(…);      /* 賃金スライドを入れない試算 */
}
```

`TINSURA`（賃金スライド）は引数。`run_pipeline.sh` は 1 を渡す。

2021年度からの規則（`kaiteiritu_make`）
--------------------------------------
```c
if( nenrei <= UNDER_67 ) kaiteiritu = base_up_index;
else                     kaiteiritu = min( base_up_index , cpi_up_index );
```

67歳以下は賃金そのまま、68歳以上は**賃金と物価の小さい方**。
2021年度の改正で「物価が上がっても賃金が下がれば下げる」
（賃金・物価スライドの見直し）が入ったぶん。

2021年度より前（`kaiteiritu_make_before`）
------------------------------------------
```c
if(nenrei == UNDER_67) {
  if( base_up_index < 1. && base_up_index < cpi_up_index ) {
    kaiteiritu = ( cpi_up_index > 1. ) ? 1. : cpi_up_index;
  } else {
    kaiteiritu = base_up_index;
  }
}
```

**`nenrei == UNDER_67` の「ちょうど 67歳」だけ**が新規裁定の扱いで、
66歳以下は `else`（既裁定と同じ）に落ちる。`kaiteiritu_make`
（2021年度以降）は `nenrei <= UNDER_67` と**不等号**なのに、
こちらは `==`。

累積の改定率は**1歳ずつずらして掛ける**ので、67歳のところで
新規裁定の率が入り、次の年度には 68歳へ送られる。66歳以下の
欄は「まだ受給していない人」の分で、67歳の欄に追いつくまで
使われない（`Full_Pension[年度][年齢]` の年齢が受給年齢）。
この形なら `==` でも `<=` でも結果は同じになる。

**丸めの戻り値を捨てているところが3か所**
-----------------------------------------
```c
if( nendo == 2015 ) {
  kaiteiritu_tannen[…] *= 0.991;
  kaiteiritu_marume( nendo , MARUME_NENDO , kaiteiritu_tannen[…] );   /* ← 捨てている */
}
else if( nendo == 2019 ) { … *= 0.995; kaiteiritu_marume( … );  }
else if( nendo == 2020 ) { … *= 0.999; kaiteiritu_marume( … );  }
```

`kaiteiritu_marume` は**値を返す関数**で、引数の `a` は値渡し。
戻り値を使わないので**何も起きない**。2015・2019・2020年度の
マクロ経済スライドを掛けたあとの単年度改定率は、
`kaiteiritu_marume` を通した（3桁に丸めた）値に**ならない**。

`検証/原本の不具合.md` の **E1（丸め関数の戻り値を捨てている）**
の③での現れ。そのまま写す。

なお**累積の方は戻り値を使っている**（`:118-121`）ので、
累積改定率は3桁に丸まる。捨てているのは単年度のぶんだけ。

既裁定の下支え（`Kisai_Shitasasae` = 0.80）
------------------------------------------
```c
if( kaiteiritu_ruiseki[…][nenrei] < Kisai_Shitasasae * kaiteiritu_ruiseki[…][UNDER_67] ) {
  kaiteiritu_ruiseki[…][nenrei] = Kisai_Shitasasae * kaiteiritu_ruiseki[…][UNDER_67];
  kaiteiritu_tannen[…][nenrei] = kaiteiritu_ruiseki[…][nenrei]
                                 / kaiteiritu_ruiseki[nendo-1][max(nenrei-1,0)];
}
```

既裁定の年金が新規裁定の**8割**を下回らないようにする。
下支えに当たった年齢は、単年度の改定率を**割り戻して**作り直す。
`cntl.c` が `Kisai_Shitasasae = 0.80` を直書きしている。

`marume_flg` — 100円単位に丸めるかどうか
----------------------------------------
```c
for( nendo = SHONENDO ; nendo <= MARUME_NENDO ; nendo++ ) marume_flg[…] = 1;

for( nendo = MARUME_NENDO + 1 ; … ) {
  if( marume_flg[nendo-1][max(nenrei-1,0)] == 1 &&
      fabs( kaiteiritu_ruiseki[nendo][nenrei] - kaiteiritu_ruiseki[nendo-1][max(nenrei-1,0)] ) < EPSILON )
    marume_flg[…] = 1;
  else
    marume_flg[…] = 0;
}
```

`MARUME_NENDO` は 2024（実績のある最後の年度）。2024年度までは
**必ず100円単位**に丸める。2025年度以降は「**前の年度も丸めていて、
かつ累積改定率が1円も動いていない**」ときだけ丸め続ける。
一度動いたら以後ずっと丸めない（旗が伝播しない）。

`marume_hantei` の3つの枝
-------------------------
```c
if( nendo <= marume_nendo )  a = pension_marume( pension );
else if( marume_flg == 1 )   a = max( pension , pension_marume( pension ) );
else                         a = pension;
```

真ん中の枝が `max` を取るのは、**丸めで下がるのを防ぐ**ため
（`pension_marume` は四捨五入なので下がることがある）。

`pension_marume` は `floor( ( a + 50. ) / 100. ) * 100`
----------------------------------------------------
100円単位の四捨五入。`+ 50` してから切り捨てる**ので、
ちょうど 50 は上へ行く**（`.5` の丸めが 0 から遠い方ではなく
**正の無限大の方**）。負の額では違う向きになるが、年金額は
負にならない。

`round( a , n )` は `sprintf` を通す
-----------------------------------
```c
double round( double a , int n ) {
  char buf[256] = {'\\0'};
  sprintf( buf , "%.*f" , n , a );
  return strtod( buf , &p );
}
```

`<cmath>` の `round` と**同じ名前で引数が2つ**なので、
`round( a , 3 )` はこちらに解決する。`printf` の丸め
（最近接・偶数）を通すので、④の `econ.c` の `round` と同じ
（`検証/移植/README.md` の④の項）。移植版は Python の
`"%.*f"` を通す（同じ丸め）。

`econ_read` の `nendo` はループの外で読まれる
--------------------------------------------
```c
int nendo;                                   /* 初期化なし */
while ( ( read_data( buffer , fp , &data_number ) != EOF ) ) { nendo = …; … }
for( counter = nendo + 1 ; counter <= SAISHUNENDO ; counter++ ) { … }
```

経済前提のファイルが**空だと `nendo` が未初期化**のまま使われる
（B4 の仲間）。読めた最後の年度から `SAISHUNENDO`（2125年度）まで、
最後の年度の値を延ばす。

`double buffer[16]` に 17 列以上来ると溢れる
--------------------------------------------
`econ_read` の `buffer` は 16 要素。`read_data` は
`data_number` までしか書かないが、**列が 17 以上ある行**が
来ると配列の外に書き込む。同梱の `econ-3001.csv` は 10 列。
移植版は 16 を超えたら例外にする。

`Tanka_Shibou` は経済前提で動かさない
------------------------------------
```c
for( kubun = 0 ; kubun < SHIBOU_KUBUN ; kubun++ )
  Tanka_Shibou[nendo - SHONENDO][kubun] = Tanka_Shibou_Shonendo[kubun];
```

死亡一時金の単価は**改定率を掛けない**（法令で定額）。
全年度に同じ値を入れる。
"""
import math

from libc import c_atof
from setconst import (ECON_SHONENDO, EPSILON, MAX_ROREI_JUKYU, N_O_NENDO,
                      SAISHUNENDO, SHIBOU_KUBUN, SHONENDO, TINSURA_KAISHI,
                      UNDER_67)
from stdfm import EOF, Buffer, NatError, c_max, read_data

__all__ = ["econ", "econ_read", "index_make", "kaiteiritu_make",
           "kaiteiritu_make_before", "kaiteiritu_marume", "marume_hantei",
           "pension_marume", "c_round_n", "rslt_out", "kaitei_out",
           "ichijikin_out"]

_CAL_START = 2004
_MARUME_NENDO = 2024
_N_ECON = SAISHUNENDO - ECON_SHONENDO + 1       # 125
_N_NENREI = MAX_ROREI_JUKYU + 1                 # 116


def c_round_n(a, n):
    """econ.c:411 の `round( double a , int n )` の忠実移植。

    `sprintf( "%.*f" )` → `strtod` を通すので、**printf の丸め**
    （最近接・端数は偶数へ）になる。`<cmath>` の `round`
    （0 から遠い方へ）とは違う。
    """
    return c_atof("%.*f" % (n, a))


def pension_marume(a):
    """econ.c:424 の忠実移植。100円単位に丸める。

    `floor( ( a + 50. ) / 100. ) * 100`。ちょうど 50 は上へ。
    """
    return math.floor((a + 50.) / 100.) * 100


def kaiteiritu_marume(nendo, marume_nendo, a):
    """econ.c:434 の忠実移植。`marume_nendo` までなら3桁に丸める。"""
    if nendo <= marume_nendo:
        a = c_round_n(a, 3)
    return a


def econ_read(fp, cpi_up, base_up_real):
    """econ.c:446 の忠実移植。経済前提を読んで最後の年度の値を延ばす。"""
    buf = Buffer(16)        # 原本は `double buffer[16]`
    nendo = None            # 原本は初期化なし（空ファイルだと未初期化）

    while read_data(buf, fp) != EOF:
        if buf.data_number >= 16:
            raise NatError(
                "econ_read: 列が %d 個ある（`double buffer[16]` の外）。"
                "原本は配列の外に書き込む" % (buf.data_number + 1))
        nendo = int(buf.num[0]) + 2000
        cpi_up[nendo - ECON_SHONENDO] = 1. + buf.num[6] / 100.
        base_up_real[nendo - ECON_SHONENDO] = 1. + buf.num[5] / 100.

    if nendo is None:
        raise NatError("econ_read: 1行も読めなかった。原本は未初期化の "
                       "`nendo` を読む")

    for counter in range(nendo + 1, SAISHUNENDO + 1):
        cpi_up[counter - ECON_SHONENDO] = cpi_up[nendo - ECON_SHONENDO]
        base_up_real[counter - ECON_SHONENDO] = \
            base_up_real[nendo - ECON_SHONENDO]


# `index_make` の中の直書き（econ.c:478-480）。保険料率の引き上げ
_HIKIAGE_START = 2003
_HIKIAGE_END = 2017
_HOKENRYO = (0.1358, 0.13934, 0.14288, 0.14642, 0.14996, 0.1535, 0.15704,
             0.16058, 0.16412, 0.16766, 0.1712, 0.17474, 0.17828, 0.18182,
             0.183)
_KASYOBUN_START = 0.910


def index_make(base_up_real, cpi_up, base_up_index, cpi_up_index,
               marume_nendo):
    """econ.c:474 の忠実移植。名目賃金と物価の指数を作る。

    `base_up_index` は「**3年平均の実質賃金上昇率 × 可処分所得割合の
    変化 × 前年の物価上昇率**」。厚生年金の被保険者の手取りの伸びに
    合わせるため、保険料率の引き上げ（2003〜2017年度）のぶんを
    `kashobun_henka` で割り戻している。

    ```c
    kashobun_henka[…] = ( ( KASYOBUN_START - HOKENRYO[nendo - 3 - HIKIAGE_START] / 2. )
                        / ( KASYOBUN_START - HOKENRYO[nendo - 4 - HIKIAGE_START] / 2. ) );
    ```

    `KASYOBUN_START` = 0.910（可処分所得の割合）から保険料率の
    **半分**（本人負担）を引いた比。`nendo - 3` と `nendo - 4` を
    見るのは、賃金の3年平均が2〜4年前を見るため。

    2005・2006年度だけ 1.0 を直に入れる（**実績がその形だった**）。
    """
    kashobun_henka = [0.0] * _N_ECON
    base_up_avg = [0.0] * _N_ECON

    for nendo in range(ECON_SHONENDO + 4, SAISHUNENDO + 1):
        if nendo == 2005 or nendo == 2006:
            base_up_avg[nendo - ECON_SHONENDO] = 1.
            kashobun_henka[nendo - ECON_SHONENDO] = 1.
        else:
            base_up_avg[nendo - ECON_SHONENDO] = (
                base_up_real[nendo - 4 - ECON_SHONENDO]
                * base_up_real[nendo - 3 - ECON_SHONENDO]
                * base_up_real[nendo - 2 - ECON_SHONENDO])

            base_up_avg[nendo - ECON_SHONENDO] = pow(
                base_up_avg[nendo - ECON_SHONENDO], 1. / 3.)

            if nendo < _HIKIAGE_END + 4:
                kashobun_henka[nendo - ECON_SHONENDO] = (
                    (_KASYOBUN_START
                     - _HOKENRYO[nendo - 3 - _HIKIAGE_START] / 2.)
                    / (_KASYOBUN_START
                       - _HOKENRYO[nendo - 4 - _HIKIAGE_START] / 2.))
            else:
                kashobun_henka[nendo - ECON_SHONENDO] = 1.

        base_up_avg[nendo - ECON_SHONENDO] = kaiteiritu_marume(
            nendo, marume_nendo, base_up_avg[nendo - ECON_SHONENDO])

        kashobun_henka[nendo - ECON_SHONENDO] = kaiteiritu_marume(
            nendo, marume_nendo, kashobun_henka[nendo - ECON_SHONENDO])

    for nendo in range(ECON_SHONENDO + 4, SAISHUNENDO + 1):
        base_up_index[nendo - ECON_SHONENDO] = (
            cpi_up[nendo - 1 - ECON_SHONENDO]
            * kashobun_henka[nendo - ECON_SHONENDO]
            * base_up_avg[nendo - ECON_SHONENDO])

        cpi_up_index[nendo - ECON_SHONENDO] = cpi_up[nendo - 1 - ECON_SHONENDO]

        base_up_index[nendo - ECON_SHONENDO] = kaiteiritu_marume(
            nendo, marume_nendo, base_up_index[nendo - ECON_SHONENDO])

        cpi_up_index[nendo - ECON_SHONENDO] = kaiteiritu_marume(
            nendo, marume_nendo, cpi_up_index[nendo - ECON_SHONENDO])


def kaiteiritu_make_before(nenrei, base_up_index, cpi_up_index):
    """econ.c:340 の忠実移植。2021年度より前の改定率の決め方。

    **`nenrei == UNDER_67` の「ちょうど 67歳」だけ**が新規裁定の扱い
    （下の `kaiteiritu_make` は `<=` で不等号）。
    """
    if nenrei == UNDER_67:
        if base_up_index < 1. and base_up_index < cpi_up_index:
            if cpi_up_index > 1.:
                kaiteiritu = 1.
            else:
                kaiteiritu = cpi_up_index
        else:
            kaiteiritu = base_up_index
    else:
        if cpi_up_index > base_up_index and base_up_index >= 1.:
            kaiteiritu = base_up_index
        elif cpi_up_index > 1. and base_up_index < 1.:
            kaiteiritu = 1.
        else:
            kaiteiritu = cpi_up_index
    return kaiteiritu


def kaiteiritu_make(nenrei, base_up_index, cpi_up_index):
    """econ.c:382 の忠実移植。2021年度以降の改定率の決め方。"""
    if nenrei <= UNDER_67:
        kaiteiritu = base_up_index
    else:
        if cpi_up_index > base_up_index:
            kaiteiritu = base_up_index
        else:
            kaiteiritu = cpi_up_index
    return kaiteiritu


def marume_hantei(nendo, marume_nendo, marume_flg, pension):
    """econ.c:404 の忠実移植。100円単位に丸めるかどうかを決める。"""
    if nendo <= marume_nendo:
        a = pension_marume(pension)
    elif marume_flg == 1:
        # 丸めで下がらないように大きい方を採る
        a = c_max(pension, pension_marume(pension))
    else:
        a = pension
    return a


def econ(G):
    """econ.c:42 の忠実移植。"""
    marume_flg = [[0] * _N_NENREI
                  for _i in range(SAISHUNENDO - SHONENDO + 1)]

    cpi_up = [0.0] * _N_ECON
    base_up_real = [0.0] * _N_ECON
    cpi_up_index = [0.0] * _N_ECON
    base_up_index = [0.0] * _N_ECON
    kaiteiritu_ruiseki = [[0.0] * _N_NENREI for _i in range(_N_ECON)]

    TINSURA_NENDO = TINSURA_KAISHI

    kt = G.kaiteiritu_tannen

    econ_read(G.fp_in[0], cpi_up, base_up_real)         # KEIZAI = 0

    index_make(base_up_real, cpi_up, base_up_index, cpi_up_index,
               _MARUME_NENDO)

    nendo = _CAL_START

    for nenrei in range(0, MAX_ROREI_JUKYU + 1):
        kt[nendo - ECON_SHONENDO][nenrei] = 1.
        kaiteiritu_ruiseki[nendo - ECON_SHONENDO][nenrei] = 1.

    for nendo in range(_CAL_START + 1, SAISHUNENDO + 1):
        for nenrei in range(0, MAX_ROREI_JUKYU + 1):
            if G.TINSURA == 1:
                if nendo < TINSURA_NENDO:
                    kt[nendo - ECON_SHONENDO][nenrei] = \
                        kaiteiritu_make_before(
                            nenrei, base_up_index[nendo - ECON_SHONENDO],
                            cpi_up_index[nendo - ECON_SHONENDO])
                else:
                    kt[nendo - ECON_SHONENDO][nenrei] = kaiteiritu_make(
                        nenrei, base_up_index[nendo - ECON_SHONENDO],
                        cpi_up_index[nendo - ECON_SHONENDO])
            else:
                kt[nendo - ECON_SHONENDO][nenrei] = kaiteiritu_make_before(
                    nenrei, base_up_index[nendo - ECON_SHONENDO],
                    cpi_up_index[nendo - ECON_SHONENDO])

            # 原本は `kaiteiritu_marume(...)` の**戻り値を捨てている**
            # （E1）。掛けるだけで3桁に丸まらない。そのまま写す
            if nendo == 2015:
                kt[nendo - ECON_SHONENDO][nenrei] *= 0.991
                kaiteiritu_marume(nendo, _MARUME_NENDO,
                                  kt[nendo - ECON_SHONENDO][nenrei])
            elif nendo == 2019:
                kt[nendo - ECON_SHONENDO][nenrei] *= 0.995
                kaiteiritu_marume(nendo, _MARUME_NENDO,
                                  kt[nendo - ECON_SHONENDO][nenrei])
            elif nendo == 2020:
                kt[nendo - ECON_SHONENDO][nenrei] *= 0.999
                kaiteiritu_marume(nendo, _MARUME_NENDO,
                                  kt[nendo - ECON_SHONENDO][nenrei])

            kaiteiritu_ruiseki[nendo - ECON_SHONENDO][nenrei] = \
                kaiteiritu_marume(
                    nendo, _MARUME_NENDO,
                    kaiteiritu_ruiseki[nendo - 1 - ECON_SHONENDO][
                        int(c_max(nenrei - 1, 0))]
                    * kt[nendo - ECON_SHONENDO][nenrei])

            if (kaiteiritu_ruiseki[nendo - ECON_SHONENDO][nenrei]
                    < G.Kisai_Shitasasae
                    * kaiteiritu_ruiseki[nendo - ECON_SHONENDO][UNDER_67]):
                kaiteiritu_ruiseki[nendo - ECON_SHONENDO][nenrei] = (
                    G.Kisai_Shitasasae
                    * kaiteiritu_ruiseki[nendo - ECON_SHONENDO][UNDER_67])

                kt[nendo - ECON_SHONENDO][nenrei] = (
                    kaiteiritu_ruiseki[nendo - ECON_SHONENDO][nenrei]
                    / kaiteiritu_ruiseki[nendo - 1 - ECON_SHONENDO][
                        int(c_max(nenrei - 1, 0))])

    for nendo in range(SHONENDO, _MARUME_NENDO + 1):
        for nenrei in range(0, MAX_ROREI_JUKYU + 1):
            marume_flg[nendo - SHONENDO][nenrei] = 1

    for nendo in range(_MARUME_NENDO + 1, SAISHUNENDO + 1):
        for nenrei in range(0, MAX_ROREI_JUKYU + 1):
            if (marume_flg[nendo - 1 - SHONENDO][
                    int(c_max(nenrei - 1, 0))] == 1
                and math.fabs(
                    kaiteiritu_ruiseki[nendo - ECON_SHONENDO][nenrei]
                    - kaiteiritu_ruiseki[nendo - 1 - ECON_SHONENDO][
                        int(c_max(nenrei - 1, 0))]) < EPSILON):
                marume_flg[nendo - SHONENDO][nenrei] = 1
            else:
                marume_flg[nendo - SHONENDO][nenrei] = 0

    for nendo in range(SHONENDO, SAISHUNENDO + 1):
        for nenrei in range(0, MAX_ROREI_JUKYU + 1):
            seinendo = nendo - nenrei

            Pension_Temp = (
                G.Full_Pension_Shonendo[nendo - SHONENDO][
                    0 if seinendo < N_O_NENDO else seinendo - N_O_NENDO]
                * kaiteiritu_ruiseki[nendo - ECON_SHONENDO][nenrei])

            G.Full_Pension[nendo - SHONENDO][nenrei] = marume_hantei(
                nendo, _MARUME_NENDO,
                marume_flg[nendo - SHONENDO][nenrei], Pension_Temp)

            Tanka_12shi = (G.Kakyu_Tanka_12shi_Shonendo
                           * kaiteiritu_ruiseki[nendo - ECON_SHONENDO][
                               UNDER_67])

            Tanka_3shiiko = (G.Kakyu_Tanka_3shiiko_Shonendo
                             * kaiteiritu_ruiseki[nendo - ECON_SHONENDO][
                                 UNDER_67])

            G.Kakyu_Tanka_12shi[nendo - SHONENDO][nenrei] = marume_hantei(
                nendo, _MARUME_NENDO,
                marume_flg[nendo - SHONENDO][UNDER_67], Tanka_12shi)

            G.Kakyu_Tanka_3shiiko[nendo - SHONENDO][nenrei] = marume_hantei(
                nendo, _MARUME_NENDO,
                marume_flg[nendo - SHONENDO][UNDER_67], Tanka_3shiiko)

        for kubun in range(0, SHIBOU_KUBUN):
            G.Tanka_Shibou[nendo - SHONENDO][kubun] = \
                G.Tanka_Shibou_Shonendo[kubun]

    # KAITEI = 8, PENSION = 10（`mfile_open.h`）
    rslt_out(G.fp_out[8], kt, _CAL_START + 1, ECON_SHONENDO, SAISHUNENDO)

    kaitei_out(G.fp_out[10], kt, _CAL_START, ECON_SHONENDO, SAISHUNENDO,
               "年金額改定率")
    kaitei_out(G.fp_out[10], kaiteiritu_ruiseki, _CAL_START, ECON_SHONENDO,
               SAISHUNENDO, "累積改定率")
    kaitei_out(G.fp_out[10], G.Full_Pension, SHONENDO, SHONENDO,
               SAISHUNENDO, "基礎年金単価")
    kaitei_out(G.fp_out[10], G.Kakyu_Tanka_12shi, SHONENDO, SHONENDO,
               SAISHUNENDO, "加給単価（第１・２子）")
    kaitei_out(G.fp_out[10], G.Kakyu_Tanka_3shiiko, SHONENDO, SHONENDO,
               SAISHUNENDO, "加給単価（第３子以降）")
    ichijikin_out(G.fp_out[10], G.Tanka_Shibou, SHONENDO, SHONENDO,
                  SAISHUNENDO, "死亡一時金単価", G.Option)


def _e(x):
    """C の `%20.14e`。Python の `%` は指数を2桁以上で書くので同じ。"""
    return "%20.14e" % x


def rslt_out(fp, output_array, shonendo, array_shonendo, saishunendo):
    """econ.c:424 の忠実移植。67歳〜115歳の欄だけを出す。

    各行の末尾にも**カンマが付く**（`"%20.14e,"` なので）。
    """
    for nendo in range(shonendo, saishunendo + 1):
        fp.write("%d," % (nendo - 2000))
        for nenrei in range(UNDER_67, MAX_ROREI_JUKYU + 1):
            fp.write("%s," % _e(output_array[nendo - array_shonendo][nenrei]))
        fp.write("\n")


def kaitei_out(fp, output_array, shonendo, array_shonendo, saishunendo,
               title):
    """econ.c:450 の忠実移植。0歳〜115歳の欄を見出し付きで出す。"""
    fp.write("%s\n%s" % (title, "年度（下2桁）"))
    for nenrei in range(0, MAX_ROREI_JUKYU + 1):
        fp.write(",%d歳" % nenrei)
    fp.write("\n")

    for nendo in range(shonendo, saishunendo + 1):
        fp.write("%d," % (nendo - 2000))
        for nenrei in range(0, MAX_ROREI_JUKYU + 1):
            fp.write("%s," % _e(output_array[nendo - array_shonendo][nenrei]))
        fp.write("\n")


# econ.c:494-496
_ICHIJIKIN_KUBUN = ("36月以上180月未満", "180月以上240月未満",
                    "240月以上300月未満", "300月以上360月未満",
                    "360月以上420月未満", "420月以上")


def ichijikin_out(fp, shibou, shonendo, array_shonendo, saishunendo, title,
                  option):
    """econ.c:490 の忠実移植。死亡一時金の単価を出す。

    `option == 1` のとき見出しに `"480月未満,480月以上"` を
    **カンマなしで**足すので、最後の区分の見出しが
    `"420月以上480月未満"` につながる（意図どおり）。
    中身も1列増える。
    """
    fp.write("%s\n%s" % (title, "年度（下2桁）"))

    for kubun in range(0, SHIBOU_KUBUN - 1):
        fp.write(",%s" % _ICHIJIKIN_KUBUN[kubun])

    if option == 1:
        fp.write("480月未満,480月以上")

    fp.write("\n")

    for nendo in range(shonendo, saishunendo + 1):
        fp.write("%d" % (nendo - 2000))

        for kubun in range(0, SHIBOU_KUBUN - 1):
            fp.write(",%s" % _e(shibou[nendo - array_shonendo][kubun]))

        if option == 1:
            fp.write(",%s" % _e(shibou[nendo - array_shonendo][
                SHIBOU_KUBUN - 1]))

        fp.write("\n")
