# -*- coding: utf-8 -*-
"""
国民年金/noufuritu.c の忠実移植（納付率と免除の対象割合）
==========================================================
1,535 行・21 個の関数。③でいちばん大きい。第1号被保険者の

    Noufuritu[種別][年度][年齢][納付区分]   納付率・免除割合
    Noufuritu_Fuka[種別][年度][年齢]        付加年金の納付率
    Hiho_Sankyu_Sum[年度]                   産前産後免除の人数
    Hiho_Ikukyu[年齢] / Hiho_Ikukyu_Sum[年度]  育児期間免除の人数

を作る。第3号は「全部納付」で済むので `noufuritu_3gou_cal` が
`NOUFU` に 1.0、ほかに 0.0 を入れるだけ。

納付区分（`menjo_jokyo`）の 0〜10
---------------------------------
| 値 | 名前 | 保険料を納めるか |
|---|---|---|
| 0 | `SUM` 計 | — |
| 1 | `NOUFU` 全額納付 | 納める |
| 2 | `MENJO_3_4` 4分の3免除 | 4分の1納める |
| 3 | `MENJO_1_2` 半額免除 | 半額納める |
| 4 | `MENJO_1_4` 4分の1免除 | 4分の3納める |
| 5 | `MENJO_HOUTEI` 法定免除 | 納めない |
| 6 | `MENJO_SHINSEI` 申請全額免除 | 納めない |
| 7 | `GAKUSEI` 学生納付特例 | 納めない |
| 8 | `WAKAMONO` 若年者納付猶予 | 納めない |
| 9 | `SANKYU` 産前産後免除 | 納めない（納付扱い） |
| 10 | `IKUKYU` 育児期間免除 | 納めない（納付扱い） |

**`NOUFU_KUBUN` = 5** が境目で、1〜4 が「保険料を納める区分」、
5〜10 が「納めない区分」。`noufuritu_cal` は 1〜4 だけ、
`taishou_wariai_cal` は 5〜10 だけを受ける（範囲外なら `exit(1)`）。

年齢の上限（`MAX_NENREI`）
-------------------------
```c
static int MAX_NENREI_BEFORE[MENJO_JOKYO] = {70,70,60,60,60,60,60,60,30,60,60};
static int MAX_NENREI_AFTER [MENJO_JOKYO] = {70,70,60,60,60,60,60,60,50,60,60};
```

`WAKAMONO`（添字 8）だけ **30 → 50**。2016年度
（`WAKAMONO_HENKO_NENDO`）に若年者納付猶予の年齢の上限が
30歳から50歳に上がった。ほかの区分は 60歳（拠出の上限）、
`SUM` と `NOUFU` は 70。

45年化のときは `MAX_NENREI_OP` に `encho_year( nendo )` を足す。
ただし **`SUM` `NOUFU` `WAKAMONO` には足さない**
（`menjo_jokyo != SUM && != NOUFU && != WAKAMONO` の条件）。

`Noufuritu` に何が入るか
------------------------
出口の2本の式（`:548-565`）。

```c
Noufuritu[…][noufu_kubun] = noufuritu_cal( … );        /* 1〜4 */
Noufuritu[…][menjo_jokyo] = taishou_wariai_cal( … );   /* 5〜10 */
```

`noufuritu_cal` は「対象割合 × 納付率」＋（`NOUFU` なら追納と
産前産後・育児期間のぶん）。`taishou_wariai_cal` は「対象割合」
から追納で納付に回ったぶんを引く。**つまり `Noufuritu` は
「被保険者に対する割合」**で、全部足すと（`SUM` を除いて）1 に
なるように作ってある。

追納（`tuinou_make`）は `[1]` を1回・`[2]` を10回足す
----------------------------------------------------
```c
for( counter = 0 ; counter <= TUINOU_NENSU ; counter++ ) {
  tuinou_kubun = ( counter == 0 ) ? 1 : 2;
  value += tuinouritu_zisseki[seibetu][tuinou_kubun][nenrei - MIN_HIHO_NENREI][menjo_jokyo];
}
```

`TUINOU_NENSU` は 10 なので `counter` は 0〜10 の 11 回。
`counter == 0` の1回だけ `[1]`（過年度納付）、残り10回は
`[2]`（追納）。**同じ値を10回足す**形で「10年ぶん追納できる」を
表している。`value = z[1] + 10 * z[2]` と書くと丸めが変わるので
**11回足す順のまま**写す。

`noufuritu_hiho_make` の `[SUM]` は足し込むだけで誰も読まない
-------------------------------------------------------------
```c
noufuritu_hiho[seibetu][nenrei - MIN_HIHO_NENREI][SUM]
 += noufuritu_hiho[seibetu][nenrei - MIN_HIHO_NENREI][noufu_kubun];
```

`noufuritu_hiho` は `noufuritu_1gou_cal` の局所で **0 に初期化
されるのは1回だけ**。`noufuritu_hiho_make` は（年度 × 性別）で
呼ばれるので、`[SUM]` は**年度をまたいで足し込まれ続ける**
（104年度ぶん積み上がる）。

しかし `[SUM]`（添字 0）を読むところが無い。`noufuritu_cal` は
`noufu_kubun` を 1〜4 でしか受けない（0 を渡すと `exit` はしないが、
呼ぶ側が 1〜4 でしか呼ばない）。**結果に影響しないが、
`[SUM]` に入る値は意味の無い数**。`検証/原本の不具合.md` の
新しい項（D の仲間）。そのまま写す。

死んだ関数が2つ
---------------
- `taishou_hosei_jisseki`（`:855-914`。前方宣言あり・**呼ばれない**）
- `taishou_mokuhyo_set`（`:702-737`。**前方宣言も無く・呼ばれない**）

どちらも `taishou_mokuhyo`（足下の免除状況別対象者数の目標）を
使う。目標に合わせる作りから、**前年度からの伸ばし方**
（`taishou_hosei`）に替えたときの置き忘れと読める。
`検証/原本の不具合.md` の新しい項（F の仲間）。
移植版は `NotImplementedError` にして残す。

`noufu_hosei` の使わない局所が2つ
---------------------------------
```c
double noufusha[SEIBETU][…][NOUFU_KUBUN] = {0.};
double noufu_taishousha[SEIBETU][…][NOUFU_KUBUN] = {0.};
```

宣言して 0 で埋めるだけで**1回も読み書きしない**（F7 の仲間）。
移植版は書かない（コメントで残す）。

`ikukyu_taishou_cal_m` の 0 割り
--------------------------------
```c
ratio = hiho_ikukyu[nenrei - MIN_HIHO_NENREI] * 4. / 3.;
ratio /= hiho_ninzu;
```

`hiho_ninzu` のゼロを見ていない（`nenkin_fdiv` を使っていない）。
分子も 0 なら `0/0` で NaN になる。60歳超の年齢では
`taishou_wariai` が 0 になるので**実際に 0 / 0 が起きうる**。
そのあと `ratio` を掛けるので NaN が広がる……が、掛ける相手の
`taishou_wariai` が 0 なので `0 * NaN = NaN` で**NaN が入る**。
移植版もそのまま写す（C と同じ NaN になるか突き合わせで見る）。

`maternity_set` は 15〜19歳の行を読んで捨てる
--------------------------------------------
```c
for( nenrei = MIN_BIRTH_NENREI ; nenrei < MAX_BIRTH_NENREI ; nenrei++ ) {
  buffer_set1( buffer , fp , &data_number , nenrei , "出生率" );
  if( nenrei >= (int) max( MIN_HIHO_NENREI , MIN_BIRTH_NENREI ) && … ) { … }
}
```

`MIN_BIRTH_NENREI` = 15 から読むが、入れるのは
`max( 20 , 15 )` = 20 以上。**15〜19歳の5行は読み捨てる**
（第1号被保険者は20歳からなので正しい）。
`max`/`min` は `stdfm.c` の `double` 版なので `(int)` で戻す。

`fuka_set` が引数ではなくグローバルを触る
----------------------------------------
```c
int fuka_set( int shubetu , FILE *fp , int option ,
	double noufuritu_fuka[…] )
{
  …
  noufuritu_fuka[shubetu][…] = buffer[2];        /* 引数を使う */
  …
  if( option == 1 ) {
    Noufuritu_Fuka[shubetu][…] = Noufuritu_Fuka[shubetu][…];   /* グローバル */
  }
}
```

前半は引数の `noufuritu_fuka`、45年化の枝は**グローバルの
`Noufuritu_Fuka`** を直に触る。呼ぶ側が
`fuka_set( shubetu , … , Noufuritu_Fuka )` と渡しているので
**同じ配列**で、結果は変わらない。移植版も同じ姿にする
（`G.Noufuritu_Fuka` を渡し、45年化の枝もそれを触る）。
"""
import numpy as np

from setconst import (BUFFER_MAX, EPSILON, GAKUSEI, IKUKYU,
                      IKUKYU_HENKO_NENDO, IKUKYU_HENKO_RITU,
                      MAX_HIHO_NENREI, MAX_KYOSHUTU_NENREI,
                      MENJO_1_2, MENJO_1_4, MENJO_3_4,
                      MENJO_HOUTEI, MENJO_JOKYO, MENJO_SHINSEI,
                      MIN_HIHO_NENREI, MIN_WAKU_NENREI, NENDO_JISSEKI,
                      NOUFU, NOUFU_KUBUN, ONNA, ONNA_1GOU, OTOKO,
                      OTOKO_1GOU, OTOKO_3GOU, ONNA_3GOU, SAISHUNENDO,
                      SANKYU, SEIBETU, SHONENDO, SOTOWAKU_SHONENDO, START,
                      SUIKEISHONENDO, SUM, TUINOU_NENSU,
                      TUINOU_NENSU_KUBUN, WAKAMONO, WAKAMONO_HENKO_NENDO,
                      WAKAMONO_HENKO_RITU)
from stdfm import (Buffer, NatError, buffer_set1, buffer_set2, c_max, c_min,
                   data_skip, encho_year, extendb, extendc, nenkin_fdiv)

__all__ = ["noufuritu"]

_N_NENDO = SAISHUNENDO - SHONENDO + 1               # 106
_N_NENREI = MAX_HIHO_NENREI - MIN_HIHO_NENREI + 1   # 51

# `mfile_open.h` の入力・出力番号
_NOUFU_MENJO_WARIAI = 13
_TUINOU = 14
_MOKUHYOUNOUFUSAISHU = 15
_FUKANOUFU = 16
_BIRTH = 12
_BUNPU = 9

# noufuritu.c:15-18 の static
_MAX_NENREI_BEFORE = (70, 70, 60, 60, 60, 60, 60, 60, 30, 60, 60)
_MAX_NENREI_AFTER = (70, 70, 60, 60, 60, 60, 60, 60, 50, 60, 60)


def seibetu_to_shubetu_1gou(seibetu):
    """noufuritu.c:1425 の忠実移植。性別 → 第1号の種別。"""
    if seibetu == OTOKO:
        return OTOKO_1GOU
    elif seibetu == ONNA:
        return ONNA_1GOU
    raise NatError("性別が範囲外です：seibetu=%d" % seibetu)


def noufuritu(G):
    """noufuritu.c:107 の忠実移植。"""
    # `static` の2本（`MAX_NENREI` と `MAX_NENREI_OP`）
    MAX_NENREI = np.zeros((_N_NENDO, MENJO_JOKYO), dtype=np.int64)
    MAX_NENREI_OP = np.zeros((_N_NENDO, MENJO_JOKYO), dtype=np.int64)

    for nendo in range(SHONENDO, SAISHUNENDO + 1):
        for menjo_jokyo in range(SUM, MENJO_JOKYO):
            if nendo < WAKAMONO_HENKO_NENDO:
                MAX_NENREI[nendo - SHONENDO, menjo_jokyo] = \
                    _MAX_NENREI_BEFORE[menjo_jokyo]
            else:
                MAX_NENREI[nendo - SHONENDO, menjo_jokyo] = \
                    _MAX_NENREI_AFTER[menjo_jokyo]

            if (menjo_jokyo != SUM and menjo_jokyo != NOUFU
                    and menjo_jokyo != WAKAMONO):
                MAX_NENREI_OP[nendo - SHONENDO, menjo_jokyo] = (
                    MAX_NENREI[nendo - SHONENDO, menjo_jokyo]
                    + encho_year(G, nendo))
            else:
                MAX_NENREI_OP[nendo - SHONENDO, menjo_jokyo] = \
                    MAX_NENREI[nendo - SHONENDO, menjo_jokyo]

    _noufuritu_3gou_cal(G, OTOKO_3GOU)
    _noufuritu_3gou_cal(G, ONNA_3GOU)

    _noufuritu_1gou_cal(G, MAX_NENREI, MAX_NENREI_OP)


def _noufuritu_3gou_cal(G, shubetu):
    """noufuritu.c:152 の忠実移植。第3号は「全部納付」。

    拠出年齢の上限（60歳＋45年化の伸び）までは `NOUFU` に 1.0、
    それ以外は 0.0。
    """
    Noufuritu = G.Noufuritu
    for nendo in range(SHONENDO, SAISHUNENDO + 1):
        MAX_3GOU_NENREI = 60 + encho_year(G, nendo)

        for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
            for menjo_jokyo in range(SUM, MENJO_JOKYO):
                if nenrei <= MAX_3GOU_NENREI:
                    if menjo_jokyo == NOUFU:
                        Noufuritu[shubetu, nendo - SHONENDO,
                                  nenrei - MIN_HIHO_NENREI,
                                  menjo_jokyo] = 1.
                    else:
                        Noufuritu[shubetu, nendo - SHONENDO,
                                  nenrei - MIN_HIHO_NENREI,
                                  menjo_jokyo] = 0.
                else:
                    Noufuritu[shubetu, nendo - SHONENDO,
                              nenrei - MIN_HIHO_NENREI, menjo_jokyo] = 0.


def _noufuritu_1gou_cal(G, MAX_NENREI, MAX_NENREI_OP):
    """noufuritu.c:200 の忠実移植。第1号の納付率を年度ごとに作る。"""
    Noufuritu = G.Noufuritu
    Noufuritu_Fuka = G.Noufuritu_Fuka
    Sotowaku = G.Sotowaku
    Sotowaku_Jurai = G.Sotowaku_Jurai

    # 原本の局所配列（すべて `= {0.}`）
    hiho = np.zeros((SEIBETU, _N_NENREI))
    hiho_zennen = np.zeros((SEIBETU, _N_NENREI))
    hiho_jurai = np.zeros((SEIBETU, _N_NENREI))
    hiho_jurai_zennen = np.zeros((SEIBETU, _N_NENREI))
    jinko = np.zeros((SEIBETU, _N_NENREI))
    jinko_zennen = np.zeros((SEIBETU, _N_NENREI))
    sankyu_mae_taishou_wariai = np.zeros((SEIBETU, _N_NENREI, MENJO_JOKYO))
    sankyu_mae_taishou_wariai_zennen = np.zeros(
        (SEIBETU, _N_NENREI, MENJO_JOKYO))
    sankyu_mae_taishou_wariai_shonendo = np.zeros(
        (SEIBETU, _N_NENREI, MENJO_JOKYO))
    taishou_wariai = np.zeros((SEIBETU, _N_NENREI, MENJO_JOKYO))
    noufuritu_ = np.zeros((SEIBETU, _N_NENREI, NOUFU_KUBUN))
    noufuritu_shonendo = np.zeros((SEIBETU, _N_NENREI, NOUFU_KUBUN))
    noufuritu_hiho = np.zeros((SEIBETU, _N_NENREI, NOUFU_KUBUN))
    maternity_ratio = np.zeros((_N_NENDO, _N_NENREI, MENJO_JOKYO))
    tuinouritu_zisseki = np.zeros(
        (SEIBETU, TUINOU_NENSU_KUBUN, _N_NENREI, MENJO_JOKYO))
    tuinouritu = np.zeros((SEIBETU, _N_NENREI, MENJO_JOKYO))
    noufu_mokuhyo_saishu = np.zeros(_N_NENDO)

    for seibetu in range(OTOKO, ONNA + 1):
        shubetu = seibetu_to_shubetu_1gou(seibetu)

        for nendo in range(SHONENDO, SAISHUNENDO + 1):
            for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
                for menjo_jokyo in range(SUM, MENJO_JOKYO):
                    Noufuritu[shubetu, nendo - SHONENDO,
                              nenrei - MIN_HIHO_NENREI, menjo_jokyo] = 0.

                Noufuritu_Fuka[shubetu, nendo - SHONENDO,
                               nenrei - MIN_HIHO_NENREI] = 0.

    for seibetu in range(OTOKO, ONNA + 1):
        shubetu = seibetu_to_shubetu_1gou(seibetu)

        for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
            hiho[seibetu, nenrei - MIN_HIHO_NENREI] = Sotowaku[
                shubetu, SUIKEISHONENDO - SOTOWAKU_SHONENDO,
                nenrei - MIN_WAKU_NENREI]

            # 人口は「種別 − 1」（第1号の1つ手前が人口の欄）
            jinko[seibetu, nenrei - MIN_HIHO_NENREI] = Sotowaku[
                shubetu - 1, SUIKEISHONENDO - SOTOWAKU_SHONENDO,
                nenrei - MIN_WAKU_NENREI]

            if G.Option == 1:
                hiho_jurai[seibetu, nenrei - MIN_HIHO_NENREI] = \
                    Sotowaku_Jurai[
                        shubetu, SUIKEISHONENDO - SOTOWAKU_SHONENDO,
                        nenrei - MIN_WAKU_NENREI]

        _noufu_menjo_set(G, seibetu, G.fp_in[_NOUFU_MENJO_WARIAI],
                         noufuritu_shonendo,
                         sankyu_mae_taishou_wariai_shonendo)

        if shubetu == ONNA_1GOU:
            _maternity_set(G, G.fp_in[_BIRTH], maternity_ratio)

        _tuinou_set(G, seibetu, G.fp_in[_TUINOU], tuinouritu_zisseki)

        _fuka_set(G, shubetu, G.fp_in[_FUKANOUFU], G.Option, Noufuritu_Fuka)

    _noufu_mokuhyo_set(G, G.fp_in[_MOKUHYOUNOUFUSAISHU],
                       noufu_mokuhyo_saishu)

    if G.Part >= 1:
        for nendo in range(G.Part_Year, SAISHUNENDO + 1):
            if G.Part == 1:
                noufu_mokuhyo_saishu[nendo - SHONENDO] += 0.003
            elif G.Part == 2:
                noufu_mokuhyo_saishu[nendo - SHONENDO] += 0.006
            elif G.Part == 3:
                noufu_mokuhyo_saishu[nendo - SHONENDO] += 0.011
            elif G.Part == 4:
                noufu_mokuhyo_saishu[nendo - SHONENDO] += 0.032
            elif G.Part == 5:
                noufu_mokuhyo_saishu[nendo - SHONENDO] += 0.002

    for nendo in range(SUIKEISHONENDO + 1, SAISHUNENDO + 1):
        for seibetu in range(OTOKO, ONNA + 1):
            shubetu = seibetu_to_shubetu_1gou(seibetu)

            for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
                hiho_zennen[seibetu, nenrei - MIN_HIHO_NENREI] = \
                    hiho[seibetu, nenrei - MIN_HIHO_NENREI]

                jinko_zennen[seibetu, nenrei - MIN_HIHO_NENREI] = \
                    jinko[seibetu, nenrei - MIN_HIHO_NENREI]

                if nenrei == MIN_HIHO_NENREI:
                    # 20歳は年度の途中で入るので半分
                    hiho[seibetu, nenrei - MIN_HIHO_NENREI] = Sotowaku[
                        shubetu, nendo - SOTOWAKU_SHONENDO,
                        nenrei - MIN_WAKU_NENREI] / 2.
                else:
                    hiho[seibetu, nenrei - MIN_HIHO_NENREI] = (
                        (Sotowaku[shubetu, nendo - 1 - SOTOWAKU_SHONENDO,
                                  nenrei - 1 - MIN_WAKU_NENREI]
                         + Sotowaku[shubetu, nendo - SOTOWAKU_SHONENDO,
                                    nenrei - MIN_WAKU_NENREI]) / 2.)

                jinko[seibetu, nenrei - MIN_HIHO_NENREI] = Sotowaku[
                    shubetu - 1, nendo - SOTOWAKU_SHONENDO,
                    nenrei - MIN_WAKU_NENREI]

                if G.Option == 1:
                    hiho_jurai_zennen[seibetu, nenrei - MIN_HIHO_NENREI] = \
                        hiho_jurai[seibetu, nenrei - MIN_HIHO_NENREI]

                    if nenrei == MIN_HIHO_NENREI:
                        hiho_jurai[seibetu, nenrei - MIN_HIHO_NENREI] = \
                            Sotowaku_Jurai[
                                shubetu, nendo - SOTOWAKU_SHONENDO,
                                nenrei - MIN_WAKU_NENREI] / 2.
                    else:
                        hiho_jurai[seibetu, nenrei - MIN_HIHO_NENREI] = (
                            (Sotowaku_Jurai[
                                shubetu, nendo - 1 - SOTOWAKU_SHONENDO,
                                nenrei - 1 - MIN_WAKU_NENREI]
                             + Sotowaku_Jurai[
                                 shubetu, nendo - SOTOWAKU_SHONENDO,
                                 nenrei - MIN_WAKU_NENREI]) / 2.)

            for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
                for menjo_jokyo in range(START, MENJO_JOKYO):
                    sankyu_mae_taishou_wariai[
                        seibetu, nenrei - MIN_HIHO_NENREI, menjo_jokyo] = \
                        sankyu_mae_taishou_wariai_shonendo[
                            seibetu, nenrei - MIN_HIHO_NENREI, menjo_jokyo]

                    if nenrei > MAX_NENREI_OP[nendo - SHONENDO,
                                              menjo_jokyo]:
                        sankyu_mae_taishou_wariai[
                            seibetu, nenrei - MIN_HIHO_NENREI,
                            menjo_jokyo] = 0.

            if nendo == WAKAMONO_HENKO_NENDO:
                # 上限が 30 → 50 になる年度は、30〜49歳を 0.75 倍にする
                for nenrei in range(_MAX_NENREI_BEFORE[WAKAMONO],
                                    _MAX_NENREI_AFTER[WAKAMONO]):
                    sankyu_mae_taishou_wariai[
                        seibetu, nenrei - MIN_HIHO_NENREI, WAKAMONO] *= \
                        WAKAMONO_HENKO_RITU

            for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
                for noufu_kubun in range(START, NOUFU_KUBUN):
                    noufuritu_[seibetu, nenrei - MIN_HIHO_NENREI,
                               noufu_kubun] = noufuritu_shonendo[
                                   seibetu, nenrei - MIN_HIHO_NENREI,
                                   noufu_kubun]

                    if nenrei > MAX_NENREI_OP[nendo - SHONENDO,
                                              noufu_kubun]:
                        noufuritu_[seibetu, nenrei - MIN_HIHO_NENREI,
                                   noufu_kubun] = 0.

        # **女 → 男の逆順**（`for( seibetu = ONNA ; seibetu >= OTOKO ; seibetu-- )`）。
        # `Hiho_Ikukyu` を女で作ってから男で足すので順に意味がある
        for seibetu in range(ONNA, OTOKO - 1, -1):
            shubetu = seibetu_to_shubetu_1gou(seibetu)

            if G.Option != 1:
                if nendo > NENDO_JISSEKI:
                    _taishou_hosei(G, seibetu, nendo,
                                   sankyu_mae_taishou_wariai,
                                   sankyu_mae_taishou_wariai_zennen,
                                   hiho, hiho_zennen, jinko, jinko_zennen)

                for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
                    for menjo_jokyo in range(START, MENJO_JOKYO):
                        sankyu_mae_taishou_wariai_zennen[
                            seibetu, nenrei - MIN_HIHO_NENREI,
                            menjo_jokyo] = sankyu_mae_taishou_wariai[
                                seibetu, nenrei - MIN_HIHO_NENREI,
                                menjo_jokyo]
            else:
                if nendo > NENDO_JISSEKI:
                    _taishou_hosei(G, seibetu, nendo,
                                   sankyu_mae_taishou_wariai,
                                   sankyu_mae_taishou_wariai_zennen,
                                   hiho_jurai, hiho_jurai_zennen,
                                   jinko, jinko_zennen)

                for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
                    for menjo_jokyo in range(START, MENJO_JOKYO):
                        sankyu_mae_taishou_wariai_zennen[
                            seibetu, nenrei - MIN_HIHO_NENREI,
                            menjo_jokyo] = sankyu_mae_taishou_wariai[
                                seibetu, nenrei - MIN_HIHO_NENREI,
                                menjo_jokyo]

                # 45年化で延びた年齢は、60歳の値か直前5年の平均で埋める
                for nenrei in range(MAX_HIHO_NENREI, MIN_HIHO_NENREI - 1,
                                    -1):
                    for menjo_jokyo in range(MENJO_3_4, GAKUSEI + 1):
                        if extendc(G, nendo, nenrei) == 1:
                            sankyu_mae_taishou_wariai[
                                seibetu, nenrei - MIN_HIHO_NENREI,
                                menjo_jokyo] = sankyu_mae_taishou_wariai[
                                    seibetu,
                                    MAX_KYOSHUTU_NENREI - MIN_HIHO_NENREI,
                                    menjo_jokyo]

                        if extendb(G, nendo, nenrei) == 1:
                            d = 0.
                            for i in range(MAX_KYOSHUTU_NENREI - 5,
                                           MAX_KYOSHUTU_NENREI):
                                d += sankyu_mae_taishou_wariai[
                                    seibetu, i - MIN_HIHO_NENREI,
                                    menjo_jokyo]
                            d /= 5.

                            sankyu_mae_taishou_wariai[
                                seibetu, nenrei - MIN_HIHO_NENREI,
                                menjo_jokyo] = d

            for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
                for menjo_jokyo in range(SUM, MENJO_JOKYO):
                    taishou_wariai[seibetu, nenrei - MIN_HIHO_NENREI,
                                   menjo_jokyo] = \
                        sankyu_mae_taishou_wariai[
                            seibetu, nenrei - MIN_HIHO_NENREI, menjo_jokyo]

            if shubetu == 5:            # ONNA_1GOU。原本は数字の直書き
                G.Hiho_Sankyu_Sum[nendo - SHONENDO] = _sankyu_taishou_cal(
                    seibetu, nendo, taishou_wariai, maternity_ratio, hiho)

                if nendo >= IKUKYU_HENKO_NENDO:
                    G.Hiho_Ikukyu_Sum[nendo - SHONENDO] = \
                        _ikukyu_taishou_cal_f(
                            seibetu, nendo, taishou_wariai,
                            sankyu_mae_taishou_wariai, maternity_ratio,
                            hiho, G.Hiho_Ikukyu)

            if shubetu == 2 and nendo >= IKUKYU_HENKO_NENDO:
                # OTOKO_1GOU。女のぶんに足す
                G.Hiho_Ikukyu_Sum[nendo - SHONENDO] += \
                    _ikukyu_taishou_cal_m(seibetu, nendo, taishou_wariai,
                                          hiho, G.Hiho_Ikukyu)

        if G.Option != 1:
            # 第5引数と第6引数に**同じ `hiho` を渡す**
            _noufu_hosei(nendo, noufu_mokuhyo_saishu, noufuritu_,
                         taishou_wariai, hiho, hiho,
                         MAX_NENREI, MAX_NENREI_OP)
        else:
            _noufu_hosei(nendo, noufu_mokuhyo_saishu, noufuritu_,
                         taishou_wariai, hiho, hiho_jurai,
                         MAX_NENREI, MAX_NENREI_OP)

            for seibetu in range(OTOKO, ONNA + 1):
                shubetu = seibetu_to_shubetu_1gou(seibetu)

                for nenrei in range(MAX_HIHO_NENREI, MIN_HIHO_NENREI - 1,
                                    -1):
                    for noufu_kubun in range(START, NOUFU_KUBUN):
                        if extendc(G, nendo, nenrei) == 1:
                            noufuritu_[seibetu, nenrei - MIN_HIHO_NENREI,
                                       noufu_kubun] = noufuritu_[
                                           seibetu,
                                           MAX_KYOSHUTU_NENREI
                                           - MIN_HIHO_NENREI, noufu_kubun]

                        if extendb(G, nendo, nenrei) == 1:
                            d = 0.
                            for i in range(MAX_KYOSHUTU_NENREI - 5,
                                           MAX_KYOSHUTU_NENREI):
                                d += noufuritu_[seibetu,
                                                i - MIN_HIHO_NENREI,
                                                noufu_kubun]
                            d /= 5.

                            noufuritu_[seibetu, nenrei - MIN_HIHO_NENREI,
                                       noufu_kubun] = d

        if G.Option == 1:
            for seibetu in range(OTOKO, ONNA + 1):
                _zengaku_noufu_cal(seibetu, nendo, taishou_wariai)

        _fuka_check(nendo, noufuritu_, taishou_wariai, Noufuritu_Fuka)

        for seibetu in range(OTOKO, ONNA + 1):
            shubetu = seibetu_to_shubetu_1gou(seibetu)

            _noufuritu_hiho_make(seibetu, noufuritu_hiho, taishou_wariai,
                                 noufuritu_)

            for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
                for menjo_jokyo in range(START, MENJO_JOKYO):
                    tuinouritu[seibetu, nenrei - MIN_HIHO_NENREI,
                               menjo_jokyo] = _tuinou_make(
                                   seibetu, nendo, nenrei, menjo_jokyo,
                                   tuinouritu_zisseki, taishou_wariai)

            for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
                for noufu_kubun in range(START, NOUFU_KUBUN):
                    Noufuritu[shubetu, nendo - SHONENDO,
                              nenrei - MIN_HIHO_NENREI, noufu_kubun] = \
                        _noufuritu_cal(seibetu, nendo, nenrei, noufu_kubun,
                                       noufuritu_hiho, taishou_wariai,
                                       tuinouritu)

                for menjo_jokyo in range(NOUFU_KUBUN, MENJO_JOKYO):
                    Noufuritu[shubetu, nendo - SHONENDO,
                              nenrei - MIN_HIHO_NENREI, menjo_jokyo] = \
                        _taishou_wariai_cal(seibetu, nendo, nenrei,
                                            menjo_jokyo, taishou_wariai,
                                            tuinouritu)

    _bunpu_data_out(G.fp_out[_BUNPU], Noufuritu, Noufuritu_Fuka)


def _noufu_menjo_set(G, seibetu, fp, noufuritu_, taishou_wariai):
    """noufuritu.c:579 の忠実移植。足元の年齢別納付率・対象割合を読む。

    `IKUKYU`（育児期間免除）の欄は**ファイルに無い**ので 0 を入れる。
    """
    SKIP_ROW = 2
    NOUFURITU_COLUMN = 1
    TAISHOU_COLUMN = 5

    buf = Buffer(BUFFER_MAX)
    shubetu = seibetu_to_shubetu_1gou(seibetu)

    if shubetu == OTOKO_1GOU:
        data_skip(fp, SKIP_ROW)

    for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
        buffer_set2(buf, fp, shubetu, nenrei, "年齢別納付率・対象割合")

        for noufu_kubun in range(START, NOUFU_KUBUN):
            noufuritu_[seibetu, nenrei - MIN_HIHO_NENREI, noufu_kubun] = \
                buf.num[NOUFURITU_COLUMN + noufu_kubun]

        for menjo_jokyo in range(START, MENJO_JOKYO):
            if menjo_jokyo == IKUKYU:
                taishou_wariai[seibetu, nenrei - MIN_HIHO_NENREI,
                               menjo_jokyo] = 0.
            else:
                taishou_wariai[seibetu, nenrei - MIN_HIHO_NENREI,
                               menjo_jokyo] = \
                    buf.num[TAISHOU_COLUMN + menjo_jokyo]
    return 0


def _noufu_mokuhyo_set(G, fp, noufu_mokuhyo):
    """noufuritu.c:629 の忠実移植。目標納付率を年度ごとに読む。"""
    SKIP_ROW = 1
    MOKUHYO_COLUMN = 1

    buf = Buffer(BUFFER_MAX)
    data_skip(fp, SKIP_ROW)

    for nendo in range(SHONENDO, SAISHUNENDO + 1):
        buffer_set1(buf, fp, nendo, "目標納付率")
        noufu_mokuhyo[nendo - SHONENDO] = buf.num[MOKUHYO_COLUMN]
    return 0


def _tuinou_set(G, seibetu, fp, tuinouritu_zisseki):
    """noufuritu.c:653 の忠実移植。追納率を読む（1行で全部）。

    `counter` は 1 と 2（過年度納付と追納）。年齢に依らず
    **同じ値を全年齢に入れる**（ファイルは1行しか無い）。
    """
    SKIP_ROW = 2

    buf = Buffer(BUFFER_MAX)
    shubetu = seibetu_to_shubetu_1gou(seibetu)

    if shubetu == OTOKO_1GOU:
        data_skip(fp, SKIP_ROW)

    buffer_set1(buf, fp, shubetu, "追納率")

    for menjo_jokyo in range(START, MENJO_JOKYO):
        for counter in range(1, 2 + 1):
            for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
                if menjo_jokyo == IKUKYU:
                    tuinouritu_zisseki[seibetu, counter,
                                       nenrei - MIN_HIHO_NENREI,
                                       menjo_jokyo] = 0.
                else:
                    tuinouritu_zisseki[seibetu, counter,
                                       nenrei - MIN_HIHO_NENREI,
                                       menjo_jokyo] = \
                        buf.num[(menjo_jokyo - 1) * 2 + counter]
    return 0


def _taishou_mokuhyo_set(*_a, **_k):
    """noufuritu.c:702 の `taishou_mokuhyo_set`。**原本で呼ばれない。**

    前方宣言も無く、`noufuritu.c` の中のどこからも呼ばれていない。
    `taishou_hosei_jisseki` と組で、「足下の免除状況別対象者数の
    目標に合わせる」作りの名残と読める。
    `検証/原本の不具合.md` の F を参照。
    """
    raise NotImplementedError(
        "taishou_mokuhyo_set は原本で呼ばれない（F）")


def _maternity_set(G, fp, maternity_ratio):
    """noufuritu.c:740 の忠実移植。出生率から産前産後の割合を作る。

    `hosei[MENJO_JOKYO] = { 0., 1., 1., 1., 1., 1., 1., 0., 1., 0., 0. }`
    で区分ごとに効かせる。`GAKUSEI`（7）`SANKYU`（9）`IKUKYU`（10）は 0。

    `2. / 3.` を掛けるのは、産前産後免除が**4か月**（1年の3分の1）
    ぶんではなく……**3分の2**。産前42日＋産後56日 ≒ 4か月に
    対して、出生率（年あたりの出生数）から「年度のうち何割が
    対象か」を出すための係数。原本のとおり写す。
    """
    SKIP_ROW = 2
    MIN_BIRTH_NENREI = 15
    MAX_BIRTH_NENREI = 50

    hosei = (0., 1., 1., 1., 1., 1., 1., 0., 1., 0., 0.)

    buf = Buffer(BUFFER_MAX)
    birth_ratio = np.zeros((_N_NENDO, _N_NENREI))

    data_skip(fp, SKIP_ROW)

    for nenrei in range(MIN_BIRTH_NENREI, MAX_BIRTH_NENREI):
        buffer_set1(buf, fp, nenrei, "出生率")

        # 15〜19歳の5行は読んで捨てる（第1号は20歳から）
        if (nenrei >= int(c_max(MIN_HIHO_NENREI, MIN_BIRTH_NENREI))
                and nenrei < int(c_min(MAX_HIHO_NENREI, MAX_BIRTH_NENREI))):
            for nendo in range(SHONENDO, SAISHUNENDO + 1):
                # 原本は代入してから掛ける（2文）
                birth_ratio[nendo - SHONENDO, nenrei - MIN_HIHO_NENREI] = \
                    buf.num[nendo - SHONENDO + 1]
                birth_ratio[nendo - SHONENDO,
                            nenrei - MIN_HIHO_NENREI] *= 2. / 3.

    for nendo in range(SHONENDO, SAISHUNENDO + 1):
        for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI):
            for menjo_jokyo in range(START, MENJO_JOKYO):
                maternity_ratio[nendo - SHONENDO,
                                nenrei - MIN_HIHO_NENREI, menjo_jokyo] = (
                    birth_ratio[nendo - SHONENDO,
                                nenrei - MIN_HIHO_NENREI]
                    * hosei[menjo_jokyo])
    return 0


def _fuka_set(G, shubetu, fp, option, noufuritu_fuka):
    """noufuritu.c:790 の忠実移植。付加年金の納付率を読む。

    足元（`SHONENDO`）の値を読んで**全年度に同じ値を延ばす**。
    45年化の枝は引数ではなく**グローバルの `Noufuritu_Fuka`** を
    触る（呼ぶ側が同じ配列を渡すので結果は同じ）。
    """
    SKIP_ROW = 1

    buf = Buffer(BUFFER_MAX)

    if shubetu == 2:            # OTOKO_1GOU。原本は数字の直書き
        data_skip(fp, SKIP_ROW)

    for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
        buffer_set2(buf, fp, shubetu, nenrei, "付加年金納付率")
        noufuritu_fuka[shubetu, SHONENDO - SHONENDO,
                       nenrei - MIN_HIHO_NENREI] = buf.num[2]

    for nendo in range(SHONENDO + 1, SAISHUNENDO + 1):
        for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
            noufuritu_fuka[shubetu, nendo - SHONENDO,
                           nenrei - MIN_HIHO_NENREI] = \
                noufuritu_fuka[shubetu, SHONENDO - SHONENDO,
                               nenrei - MIN_HIHO_NENREI]

    if option == 1:
        # 原本はここだけグローバルの `Noufuritu_Fuka` を触る
        Nf = G.Noufuritu_Fuka
        for nendo in range(SHONENDO, SAISHUNENDO + 1):
            for nenrei in range(MAX_HIHO_NENREI, MIN_HIHO_NENREI - 1, -1):
                if extendc(G, nendo, nenrei) == 1:
                    Nf[shubetu, nendo - SHONENDO,
                       nenrei - MIN_HIHO_NENREI] = Nf[
                           shubetu, nendo - SHONENDO,
                           MAX_KYOSHUTU_NENREI - MIN_HIHO_NENREI]

                if extendb(G, nendo, nenrei) == 1:
                    d = 0.
                    for i in range(MAX_KYOSHUTU_NENREI - 5,
                                   MAX_KYOSHUTU_NENREI):
                        d += Nf[shubetu, nendo - SHONENDO,
                                i - MIN_HIHO_NENREI]
                    d /= 5.

                    Nf[shubetu, nendo - SHONENDO,
                       nenrei - MIN_HIHO_NENREI] = d
    return 0


def _taishou_hosei_jisseki(*_a, **_k):
    """noufuritu.c:855 の `taishou_hosei_jisseki`。**原本で呼ばれない。**

    前方宣言（`:40`）はあるが、`noufuritu.c` の中のどこからも
    呼ばれていない。`taishou_mokuhyo_set` と組。
    `検証/原本の不具合.md` の F を参照。
    """
    raise NotImplementedError(
        "taishou_hosei_jisseki は原本で呼ばれない（F）")


def _taishou_hosei(G, seibetu, nendo, taishou_wariai,
                   taishou_wariai_zennen, hiho, hiho_zennen, jinko,
                   jinko_zennen):
    """noufuritu.c:918 の忠実移植。免除の対象割合を前年度から伸ばす。

    **法定免除と学生納付特例だけ人口の伸びに合わせる。**

    ```c
    if( menjo_jokyo == MENJO_HOUTEI ||
        ( menjo_jokyo == GAKUSEI && ( Part != 4 || nendo < Part_Year || nendo > Part_Year + 1 ) ) )
    ```

    法定免除（生活保護・障害年金の受給者）と学生は人口に比例する
    という考え。ただし**適用拡大の最大のケース（`Part == 4`）の
    2年間だけ学生を外す**（第2号に移る人が多いので前年度の値を
    そのまま使う）。ほかの区分は前年度の割合をそのまま。

    免除割合の合計が 1 を超えたら、法定免除と学生から按分して削る
    （`EPSILON` を足して確実に 1 未満にする）。
    """
    for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
        for menjo_jokyo in range(START, MENJO_JOKYO):
            if (menjo_jokyo == MENJO_HOUTEI
                    or (menjo_jokyo == GAKUSEI
                        and (G.Part != 4 or nendo < G.Part_Year
                             or nendo > G.Part_Year + 1))):
                taishou_wariai[seibetu, nenrei - MIN_HIHO_NENREI,
                               menjo_jokyo] = (
                    taishou_wariai_zennen[seibetu,
                                          nenrei - MIN_HIHO_NENREI,
                                          menjo_jokyo]
                    * hiho_zennen[seibetu, nenrei - MIN_HIHO_NENREI]
                    * nenkin_fdiv(
                        jinko[seibetu, nenrei - MIN_HIHO_NENREI],
                        jinko_zennen[seibetu, nenrei - MIN_HIHO_NENREI]))

                taishou_wariai[seibetu, nenrei - MIN_HIHO_NENREI,
                               menjo_jokyo] *= nenkin_fdiv(
                                   1.0,
                                   hiho[seibetu, nenrei - MIN_HIHO_NENREI])
            elif menjo_jokyo != NOUFU:
                taishou_wariai[seibetu, nenrei - MIN_HIHO_NENREI,
                               menjo_jokyo] = taishou_wariai_zennen[
                                   seibetu, nenrei - MIN_HIHO_NENREI,
                                   menjo_jokyo]

        menjo_sum = 0.
        for menjo_jokyo in range(START, MENJO_JOKYO):
            if menjo_jokyo != NOUFU:
                menjo_sum += taishou_wariai[seibetu,
                                            nenrei - MIN_HIHO_NENREI,
                                            menjo_jokyo]

        if menjo_sum > 1.:
            print("免除割合が１を超えています：性別%d, 年度%d, 年齢%d"
                  % (seibetu, nendo, nenrei))

            r = ((menjo_sum - 1. + EPSILON)
                 / (taishou_wariai[seibetu, nenrei - MIN_HIHO_NENREI,
                                   MENJO_HOUTEI]
                    + taishou_wariai[seibetu, nenrei - MIN_HIHO_NENREI,
                                     GAKUSEI]))

            taishou_wariai[seibetu, nenrei - MIN_HIHO_NENREI,
                           MENJO_HOUTEI] *= 1 - r
            taishou_wariai[seibetu, nenrei - MIN_HIHO_NENREI,
                           GAKUSEI] *= 1 - r

    _zengaku_noufu_cal(seibetu, nendo, taishou_wariai)


def _zengaku_noufu_cal(seibetu, nendo, taishou_wariai):
    """noufuritu.c:988 の忠実移植。`NOUFU` を「1 − 免除の合計」で出す。

    足す順は `menjo_jokyo` の 1〜10（`NOUFU` を飛ばす）。
    負になったら `exit(1)`。
    """
    shubetu = seibetu_to_shubetu_1gou(seibetu)

    for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
        taishou_wariai[seibetu, nenrei - MIN_HIHO_NENREI, NOUFU] = 1.

        for menjo_jokyo in range(START, MENJO_JOKYO):
            if menjo_jokyo != NOUFU:
                taishou_wariai[seibetu, nenrei - MIN_HIHO_NENREI,
                               NOUFU] -= taishou_wariai[
                                   seibetu, nenrei - MIN_HIHO_NENREI,
                                   menjo_jokyo]

        if taishou_wariai[seibetu, nenrei - MIN_HIHO_NENREI, NOUFU] < 0.:
            raise NatError(
                "種別%d, 年度%d, 年齢%dの全額納付対象割合がマイナスです"
                % (shubetu, nendo, nenrei))


def _sankyu_taishou_cal(seibetu, nendo, taishou_wariai, maternity_ratio,
                        hiho):
    """noufuritu.c:1025 の忠実移植。産前産後免除の人数と割合。

    各区分から `maternity_ratio × 1/3` を `SANKYU` に移す。
    `1. / 3.` は産前産後の4か月（1年の3分の1）。
    `SANKYU` と `IKUKYU` 自身は元にしない。
    """
    sankyu_ninzu = 0.

    for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
        for menjo_jokyo in range(START, MENJO_JOKYO):
            if menjo_jokyo != SANKYU and menjo_jokyo != IKUKYU:
                sankyu_ninzu += (
                    hiho[seibetu, nenrei - MIN_HIHO_NENREI]
                    * taishou_wariai[seibetu, nenrei - MIN_HIHO_NENREI,
                                     menjo_jokyo]
                    * maternity_ratio[nendo - SHONENDO,
                                      nenrei - MIN_HIHO_NENREI,
                                      menjo_jokyo]
                    * 1. / 3.)

                taishou_wariai[seibetu, nenrei - MIN_HIHO_NENREI,
                               SANKYU] += (
                    taishou_wariai[seibetu, nenrei - MIN_HIHO_NENREI,
                                   menjo_jokyo]
                    * maternity_ratio[nendo - SHONENDO,
                                      nenrei - MIN_HIHO_NENREI,
                                      menjo_jokyo]
                    * 1. / 3.)

                taishou_wariai[seibetu, nenrei - MIN_HIHO_NENREI,
                               menjo_jokyo] -= (
                    taishou_wariai[seibetu, nenrei - MIN_HIHO_NENREI,
                                   menjo_jokyo]
                    * maternity_ratio[nendo - SHONENDO,
                                      nenrei - MIN_HIHO_NENREI,
                                      menjo_jokyo]
                    * 1. / 3.)

    return sankyu_ninzu


def _ikukyu_taishou_cal_f(seibetu, nendo, taishou_wariai,
                          sankyu_mae_taishou_wariai, maternity_ratio, hiho,
                          hiho_ikukyu):
    """noufuritu.c:1064 の忠実移植。育児期間免除（女）。

    `3. / 4.` は育児期間（子が1歳になるまで）のうち産前産後の
    あとの9か月ぶん。**元にするのは `sankyu_mae_taishou_wariai`**
    （産前産後を引く前の割合）で、足す先は `taishou_wariai`。
    引くのも `taishou_wariai` なので、産前産後で引いたあとの値から
    さらに引く形になる。

    `IKUKYU_HENKO_NENDO`（2026年度）だけ `IKUKYU_HENKO_RITU`
    （0.5）を掛ける（年度の途中から始まるので半年ぶん）。
    """
    ikukyu_ninzu = 0.

    if nendo == IKUKYU_HENKO_NENDO:
        eikyo_ritu = IKUKYU_HENKO_RITU
    else:
        eikyo_ritu = 1.

    for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
        hiho_ikukyu[nenrei - MIN_HIHO_NENREI] = 0.
        for menjo_jokyo in range(START, MENJO_JOKYO):
            if menjo_jokyo != SANKYU and menjo_jokyo != IKUKYU:
                hiho_ikukyu[nenrei - MIN_HIHO_NENREI] += (
                    hiho[seibetu, nenrei - MIN_HIHO_NENREI]
                    * sankyu_mae_taishou_wariai[
                        seibetu, nenrei - MIN_HIHO_NENREI, menjo_jokyo]
                    * maternity_ratio[nendo - SHONENDO,
                                      nenrei - MIN_HIHO_NENREI,
                                      menjo_jokyo]
                    * 3. / 4. * eikyo_ritu)

                taishou_wariai[seibetu, nenrei - MIN_HIHO_NENREI,
                               IKUKYU] += (
                    sankyu_mae_taishou_wariai[
                        seibetu, nenrei - MIN_HIHO_NENREI, menjo_jokyo]
                    * maternity_ratio[nendo - SHONENDO,
                                      nenrei - MIN_HIHO_NENREI,
                                      menjo_jokyo]
                    * 3. / 4. * eikyo_ritu)

                taishou_wariai[seibetu, nenrei - MIN_HIHO_NENREI,
                               menjo_jokyo] -= (
                    sankyu_mae_taishou_wariai[
                        seibetu, nenrei - MIN_HIHO_NENREI, menjo_jokyo]
                    * maternity_ratio[nendo - SHONENDO,
                                      nenrei - MIN_HIHO_NENREI,
                                      menjo_jokyo]
                    * 3. / 4. * eikyo_ritu)

        ikukyu_ninzu += hiho_ikukyu[nenrei - MIN_HIHO_NENREI]

    return ikukyu_ninzu


def _ikukyu_taishou_cal_m(seibetu, nendo, taishou_wariai, hiho,
                          hiho_ikukyu):
    """noufuritu.c:1119 の忠実移植。育児期間免除（男）。

    女で作った `hiho_ikukyu`（年齢別の人数）を `4. / 3.` して、
    男の被保険者数で割った比を掛ける。**妻の育児期間に合わせて
    夫も免除になる**という作り。

    `hosei[MENJO_JOKYO] = { 0., 1., 1., 1., 1., 1./4., 1., 0., 1., 0., 0. }`
    で `MENJO_HOUTEI`（5）だけ **4分の1**。法定免除の人は
    もともと納めていないので効きが小さい。

    **0 割りを見ていない。**

    ```c
    ratio = hiho_ikukyu[nenrei - MIN_HIHO_NENREI] * 4. / 3.;
    ratio /= hiho_ninzu;
    ```

    `nenkin_fdiv` を使っていないので、`hiho_ninzu` が 0 だと
    `inf` か `NaN` になる。60歳超は `taishou_wariai` が 0 なので
    `0 / 0` が起きうる。そのあと掛ける相手も 0 なので
    `0 * NaN = NaN` が `taishou_wariai[IKUKYU]` に入る。
    原本のとおり写す（C と同じ値になるかは突き合わせで見る）。
    """
    ikukyu_ninzu = 0.

    hosei = (0., 1., 1., 1., 1., 1. / 4., 1., 0., 1., 0., 0.)

    for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
        hiho_ninzu = 0.
        for menjo_jokyo in range(START, MENJO_JOKYO):
            if menjo_jokyo != SANKYU and menjo_jokyo != IKUKYU:
                hiho_ninzu += (
                    hiho[seibetu, nenrei - MIN_HIHO_NENREI]
                    * taishou_wariai[seibetu, nenrei - MIN_HIHO_NENREI,
                                     menjo_jokyo]
                    * hosei[menjo_jokyo])
        ratio = hiho_ikukyu[nenrei - MIN_HIHO_NENREI] * 4. / 3.
        # 原本は 0 割りを見ていない（`nenkin_fdiv` を使っていない）
        ratio = ratio / hiho_ninzu

        for menjo_jokyo in range(START, MENJO_JOKYO):
            if menjo_jokyo != SANKYU and menjo_jokyo != IKUKYU:
                ikukyu_ninzu += (
                    hiho[seibetu, nenrei - MIN_HIHO_NENREI]
                    * taishou_wariai[seibetu, nenrei - MIN_HIHO_NENREI,
                                     menjo_jokyo]
                    * ratio * hosei[menjo_jokyo])

                taishou_wariai[seibetu, nenrei - MIN_HIHO_NENREI,
                               IKUKYU] += (
                    taishou_wariai[seibetu, nenrei - MIN_HIHO_NENREI,
                                   menjo_jokyo]
                    * ratio * hosei[menjo_jokyo])

                taishou_wariai[seibetu, nenrei - MIN_HIHO_NENREI,
                               menjo_jokyo] -= (
                    taishou_wariai[seibetu, nenrei - MIN_HIHO_NENREI,
                                   menjo_jokyo]
                    * ratio * hosei[menjo_jokyo])

    return ikukyu_ninzu


def _noufu_hosei(nendo, noufu_mokuhyo, noufuritu_, taishou_wariai, hiho,
                 hiho_hosei, MAX_NENREI, MAX_NENREI_OP):
    """noufuritu.c:1167 の忠実移植。全体の納付率を目標に合わせる。

    合計が目標より大きければ全部を比で縮め、小さければ
    「まだ納めていないぶん」から引き上げる。

    **合計を取る年齢の上限は `MAX_NENREI`、直す年齢の上限は
    `MAX_NENREI_OP`**（45年化で伸びたぶんを含む）。合計に入って
    いない年齢も直す形になっている。

    `noufusha` と `noufu_taishousha` という局所配列を 0 で確保して
    いるが**1回も読み書きしない**（F7 の仲間）。移植版は作らない。
    """
    mokuhyo = 0.
    gokei = 0.
    non_gokei = 0.
    noufu_taishou = 0.

    for seibetu in range(OTOKO, ONNA + 1):
        for noufu_kubun in range(START, NOUFU_KUBUN):
            for nenrei in range(MIN_HIHO_NENREI,
                                int(MAX_NENREI[nendo - SHONENDO,
                                               noufu_kubun]) + 1):
                noufu_taishou += (
                    taishou_wariai[seibetu, nenrei - MIN_HIHO_NENREI,
                                   noufu_kubun]
                    * hiho_hosei[seibetu, nenrei - MIN_HIHO_NENREI])

                gokei += (
                    noufuritu_[seibetu, nenrei - MIN_HIHO_NENREI,
                               noufu_kubun]
                    * taishou_wariai[seibetu, nenrei - MIN_HIHO_NENREI,
                                     noufu_kubun]
                    * hiho_hosei[seibetu, nenrei - MIN_HIHO_NENREI])

                non_gokei += (
                    (1.0 - noufuritu_[seibetu, nenrei - MIN_HIHO_NENREI,
                                      noufu_kubun])
                    * taishou_wariai[seibetu, nenrei - MIN_HIHO_NENREI,
                                     noufu_kubun]
                    * hiho_hosei[seibetu, nenrei - MIN_HIHO_NENREI])

    mokuhyo = noufu_mokuhyo[nendo - SHONENDO] * noufu_taishou

    if mokuhyo <= gokei:
        for seibetu in range(OTOKO, ONNA + 1):
            for noufu_kubun in range(START, NOUFU_KUBUN):
                for nenrei in range(MIN_HIHO_NENREI,
                                    int(MAX_NENREI_OP[nendo - SHONENDO,
                                                      noufu_kubun]) + 1):
                    noufuritu_[seibetu, nenrei - MIN_HIHO_NENREI,
                               noufu_kubun] *= nenkin_fdiv(mokuhyo, gokei)
    else:
        hikiageritu = nenkin_fdiv(mokuhyo - gokei, non_gokei)

        for seibetu in range(OTOKO, ONNA + 1):
            for noufu_kubun in range(START, NOUFU_KUBUN):
                for nenrei in range(MIN_HIHO_NENREI,
                                    int(MAX_NENREI_OP[nendo - SHONENDO,
                                                      noufu_kubun]) + 1):
                    ninzu = (
                        hiho[seibetu, nenrei - MIN_HIHO_NENREI]
                        * taishou_wariai[seibetu, nenrei - MIN_HIHO_NENREI,
                                         noufu_kubun]
                        * noufuritu_[seibetu, nenrei - MIN_HIHO_NENREI,
                                     noufu_kubun]
                        + hiho[seibetu, nenrei - MIN_HIHO_NENREI]
                        * taishou_wariai[seibetu, nenrei - MIN_HIHO_NENREI,
                                         noufu_kubun]
                        * (1.0 - noufuritu_[seibetu,
                                            nenrei - MIN_HIHO_NENREI,
                                            noufu_kubun])
                        * hikiageritu)

                    noufuritu_[seibetu, nenrei - MIN_HIHO_NENREI,
                               noufu_kubun] = nenkin_fdiv(
                                   ninzu,
                                   hiho[seibetu, nenrei - MIN_HIHO_NENREI]
                                   * taishou_wariai[
                                       seibetu, nenrei - MIN_HIHO_NENREI,
                                       noufu_kubun])


def _fuka_check(nendo, noufuritu_, taishou_wariai, noufuritu_fuka):
    """noufuritu.c:1265 の忠実移植。付加年金の納付率の上限を見る。

    付加年金は「全額納付している人」しか納められないので、
    `NOUFU × 納付率 ＋ 産前産後 ＋ 育児期間` を超えたら切り下げる。
    """
    for seibetu in range(OTOKO, ONNA + 1):
        shubetu = seibetu_to_shubetu_1gou(seibetu)

        for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
            noufu = (taishou_wariai[seibetu, nenrei - MIN_HIHO_NENREI,
                                    NOUFU]
                     * noufuritu_[seibetu, nenrei - MIN_HIHO_NENREI,
                                  NOUFU])

            noufu += taishou_wariai[seibetu, nenrei - MIN_HIHO_NENREI,
                                    SANKYU]
            noufu += taishou_wariai[seibetu, nenrei - MIN_HIHO_NENREI,
                                    IKUKYU]

            if noufu < noufuritu_fuka[shubetu, nendo - SHONENDO,
                                      nenrei - MIN_HIHO_NENREI]:
                print("付加納付率が上限を超えたため補正："
                      "性別%d, 年度%d, 年齢%d" % (seibetu, nendo, nenrei))
                noufuritu_fuka[shubetu, nendo - SHONENDO,
                               nenrei - MIN_HIHO_NENREI] = noufu


def _noufuritu_hiho_make(seibetu, noufuritu_hiho, taishou_wariai,
                         noufuritu_):
    """noufuritu.c:1300 の忠実移植。被保険者に対する納付の割合。

    **`[SUM]`（添字 0）を `+=` で足し込むが 0 に戻さない。**
    `noufuritu_hiho` は呼ぶ側の局所で1回しか 0 にされないので、
    `[SUM]` は年度をまたいで積み上がり続ける。読むところが
    無いので結果には影響しない（`検証/原本の不具合.md` の D の仲間）。
    """
    for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
        for noufu_kubun in range(START, NOUFU_KUBUN):
            noufuritu_hiho[seibetu, nenrei - MIN_HIHO_NENREI,
                           noufu_kubun] = (
                taishou_wariai[seibetu, nenrei - MIN_HIHO_NENREI,
                               noufu_kubun]
                * noufuritu_[seibetu, nenrei - MIN_HIHO_NENREI,
                             noufu_kubun])

            # 0 に戻さないので年度をまたいで積み上がる（誰も読まない）
            noufuritu_hiho[seibetu, nenrei - MIN_HIHO_NENREI, SUM] += \
                noufuritu_hiho[seibetu, nenrei - MIN_HIHO_NENREI,
                               noufu_kubun]


def _tuinou_make(seibetu, nendo, nenrei, menjo_jokyo, tuinouritu_zisseki,
                 taishou_wariai):
    """noufuritu.c:1329 の忠実移植。追納で納付に回る割合。

    `counter` を 0〜`TUINOU_NENSU`（10）の **11 回**回して、
    `counter == 0` の1回だけ `[1]`（過年度納付）、残り10回は
    `[2]`（追納）を足す。**11回足す順のまま**写す。
    """
    value = 0.

    if (menjo_jokyo != NOUFU and menjo_jokyo != SANKYU
            and menjo_jokyo != IKUKYU):
        for counter in range(0, TUINOU_NENSU + 1):
            tuinou_kubun = 1 if counter == 0 else 2

            value += tuinouritu_zisseki[seibetu, tuinou_kubun,
                                        nenrei - MIN_HIHO_NENREI,
                                        menjo_jokyo]

        value *= taishou_wariai[seibetu, nenrei - MIN_HIHO_NENREI,
                                menjo_jokyo]

    return value


def _noufuritu_cal(seibetu, nendo, nenrei, noufu_kubun, noufuritu_hiho,
                   taishou_wariai, tuinouritu):
    """noufuritu.c:1355 の忠実移植。保険料を納める区分（1〜4）の割合。

    `NOUFU`（全額納付）には、免除から追納で戻ったぶんと
    産前産後・育児期間のぶんを足す。ほかの区分は追納で
    `NOUFU` に移ったぶんを引く。
    """
    if noufu_kubun >= NOUFU_KUBUN:
        raise NatError(
            "noufuiritu_calは保険料納付のある区分が計算対象です："
            "noufu_kubun=%d" % noufu_kubun)

    value = noufuritu_hiho[seibetu, nenrei - MIN_HIHO_NENREI, noufu_kubun]

    if noufu_kubun == NOUFU:
        for menjo_jokyo in range(START, MENJO_JOKYO):
            if (menjo_jokyo != NOUFU and menjo_jokyo != SANKYU
                    and menjo_jokyo != IKUKYU):
                value += tuinouritu[seibetu, nenrei - MIN_HIHO_NENREI,
                                    menjo_jokyo]

        value += taishou_wariai[seibetu, nenrei - MIN_HIHO_NENREI, SANKYU]

        if nendo >= IKUKYU_HENKO_NENDO:
            value += taishou_wariai[seibetu, nenrei - MIN_HIHO_NENREI,
                                    IKUKYU]
    else:
        value -= tuinouritu[seibetu, nenrei - MIN_HIHO_NENREI, noufu_kubun]

    return value


def _taishou_wariai_cal(seibetu, nendo, nenrei, menjo_jokyo,
                        taishou_wariai, tuinouritu):
    """noufuritu.c:1402 の忠実移植。納めない区分（5〜10）の割合。"""
    if menjo_jokyo < NOUFU_KUBUN or menjo_jokyo >= MENJO_JOKYO:
        raise NatError(
            "taishou_wariai_calは保険料納付のない区分が計算対象です："
            "menjo_jokyo=%d" % menjo_jokyo)

    value = taishou_wariai[seibetu, nenrei - MIN_HIHO_NENREI, menjo_jokyo]

    if menjo_jokyo != SANKYU and menjo_jokyo != IKUKYU:
        value -= tuinouritu[seibetu, nenrei - MIN_HIHO_NENREI, menjo_jokyo]

    return value


# noufuritu.c:1452-1455 の見出し
_HYOTO = ("性", "年度", "年齢",
          "11", "12", "13", "14", "15", "16", "17", "18", "19", "20")


def _bunpu_data_out(fp, Noufuritu, Noufuritu_Fuka):
    """noufuritu.c:1448 の忠実移植。⑥分布推計が読むファイルを書く。

    10列（`"11"`〜`"20"`）の中身は

    | 見出し | 中身 |
    |---|---|
    | 11 | 全額納付（付加を除く） |
    | 12 | 付加年金 |
    | 13 | 法定免除 |
    | 14 | 申請全額免除 |
    | 15 | 4分の3免除 |
    | 16 | 半額免除 |
    | 17 | 4分の1免除 |
    | 18 | 学生納付特例 |
    | 19 | 若年者納付猶予 |
    | 20 | 未納（1 − 上の8つ。付加は引かない） |

    最後の列は `1.` から `NOUFU` `MENJO_HOUTEI` `MENJO_SHINSEI`
    `MENJO_3_4` `MENJO_1_2` `MENJO_1_4` `GAKUSEI` `WAKAMONO` の
    8つを**書いてある順に**引く。`SANKYU` と `IKUKYU` は
    `NOUFU` に入っているので引かない。
    """
    hyoto_num = len(_HYOTO)

    for i in range(0, hyoto_num - 1):
        fp.write("%s," % _HYOTO[i])
    fp.write("%s\n" % _HYOTO[hyoto_num - 1])

    for seibetu in range(OTOKO, ONNA + 1):
        shubetu = seibetu_to_shubetu_1gou(seibetu)

        for nendo in range(SUIKEISHONENDO, SAISHUNENDO + 1):
            for nenrei in range(MIN_HIHO_NENREI, MAX_HIHO_NENREI + 1):
                k = nendo - SHONENDO
                x = nenrei - MIN_HIHO_NENREI
                N = Noufuritu
                fp.write("%d, %d, %d" % (seibetu, nendo, nenrei))

                fp.write(", %11.9e" % (N[shubetu, k, x, NOUFU]
                                       - Noufuritu_Fuka[shubetu, k, x]))
                fp.write(", %11.9e" % Noufuritu_Fuka[shubetu, k, x])
                fp.write(", %11.9e" % N[shubetu, k, x, MENJO_HOUTEI])
                fp.write(", %11.9e" % N[shubetu, k, x, MENJO_SHINSEI])
                fp.write(", %11.9e" % N[shubetu, k, x, MENJO_3_4])
                fp.write(", %11.9e" % N[shubetu, k, x, MENJO_1_2])
                fp.write(", %11.9e" % N[shubetu, k, x, MENJO_1_4])
                fp.write(", %11.9e" % N[shubetu, k, x, GAKUSEI])
                fp.write(", %11.9e" % N[shubetu, k, x, WAKAMONO])

                fp.write(", %11.9e" % (1. - N[shubetu, k, x, NOUFU]
                                       - N[shubetu, k, x, MENJO_HOUTEI]
                                       - N[shubetu, k, x, MENJO_SHINSEI]
                                       - N[shubetu, k, x, MENJO_3_4]
                                       - N[shubetu, k, x, MENJO_1_2]
                                       - N[shubetu, k, x, MENJO_1_4]
                                       - N[shubetu, k, x, GAKUSEI]
                                       - N[shubetu, k, x, WAKAMONO]))

                fp.write("\n")
