# -*- coding: utf-8 -*-
"""
基礎年金/main.c の忠実移植（④の入口）
=======================================
呼ぶ順番がそのまま仕様なので、原本の並びを崩さずに写してある。

    cntl                  引数17個を読む
    file_open × 2         infile.csv / outfile.csv の一覧を開く
    dtst                  決め打ちの実績値と初期値
    econ                  経済前提・改定率・累積調整率
    ReadKokunen_jisseki   ③国民年金の受給者数
    ReadHiyousha × 4      ②厚生年金（厚年・国共・地共・私学）
    waku                  ①被保険者推計の外枠 → 拠出金算定対象者
    tumatumi_cal_jisseki   妻積の取り崩しと分配
    Atamawari             給付水準調整前の給付費と拠出金
    read_file             ③国民年金の独自給付・保険料
    file_write_kakyu      ⑤へ渡す拠出金ファイル
    printout( 0 )         kekka…b.csv（調整前）
    ── カットファイル ──
      kako == 0 かつ CUT_KOTEI == 0  tyousei → file_write_cut
      kako == 0 かつ CUT_KOTEI == 1  read_cut → dokuzi_cal
      kako >= 1                      read_cut → dokuzi_cal
    Atamawari             給付水準調整後の給付費と拠出金
    printout( 1 )         kekka…a.csv（調整後）

`Atamawari()` が2回呼ばれるのが要
---------------------------------
1回目は `Cut_ritu` が全部 1.0（`dtst()` の初期値）なので調整なしの
給付費、2回目は `tyousei()`／`read_cut()` が決めた `Cut_ritu` で
調整後の給付費になる。`kaiteiritu` も `tyousei()` が
`kaiteiritu_cut` に差し替えるので、2回目は改定率も調整後。

移植パッチで直したところ（`検証/実行/patches/glibc-portability.patch`）
------------------------------------------------------------------------
原本には**同じストリームを2回閉じる**箇所が3つある。どれも
glibc ではヒープが壊れて異常終了するので、UTF-8 に変換した木の側で
コメントアウトしてある。移植版も同じふるまい（閉じない）にしてある。

1. `main.c:104` の `fclose( fp_in[0] )`
   `read_file.c:328` が既に `fclose( fp_in[DOKUZI] )` している。
   `DOKUZI` は 0 なので同じストリーム。
2. `printout.c:151` の `fclose( fp_out[OUTPUT] )`
   `printout()` が2回呼ばれるので2回閉じる。
3. `read_cut.c:61-62` の `fclose( fp_in[CUT] )` と `fclose( fp_in[CUT_K] )`
   開いていない側が `NULL` のまま渡される。

原本の癖をそのまま残しているところ
----------------------------------
1. **`seido` を宣言するだけで2つのループに使い回す。**
   `KOUNEN`〜`SHIGAKU` と `KOKUNEN_1GOU`〜`SHIGAKU_3GOU` で
   意味の違う番号を同じ変数に入れる。

2. **`switch( seido )` が `cout` を出すだけ。**`default` で `exit(1)`
   するが、`for` が `KOUNEN`〜`SHIGAKU` を回るので届かない。

3. **`fclose( fp_in[zisseki_hosei] )` などを `main.c` が個別に閉じる。**
   `ReadKokunen_jisseki` と `ReadHiyousha` は自分で閉じるのに、
   `zisseki_hosei` `KEIZAI` `KAITEI` `TANNEN_CUT` は `main.c` が閉じる。

4. **`fprintf( fp_out[SETTEI] , "\\n" )` を最後に出す。**`SETTEI` は
   追記モード（`a`）なので、試算を重ねると空行が挟まる。
"""
import sys
import os

from cntl import cntl
from dtst import dtst
from econ import econ
from file_open import file_open
from glva import G
from readhiyousha import ReadHiyousha
from readkokunen_jisseki import ReadKokunen_jisseki
from waku import waku
from tumatumi_cal_jisseki import tumatumi_cal_jisseki
from atamawari import Atamawari
from read_file import read_file
from file_write_kakyu import file_write_kakyu
from printout import printout
from tyousei import tyousei
from file_write_cut import file_write_cut
from read_cut import read_cut
from dokuzi_cal import dokuzi_cal
from setconst import (
    CHIKYO, KAITEI, KEIZAI, KOKKYO, KOKUNEN_1GOU, KOUNEN, SETTEI,
    SHIGAKU, SHIGAKU_3GOU, TANNEN_CUT, zisseki_hosei,
)

__all__ = ["run", "main"]


def run(argv):
    """main.c:23 の忠実移植。`argv` は原本と同じく `argv[0]` 込みの list。"""
    print("start")
    print("cntl")
    cntl(argv)

    print("The version number of this run is %s-%s."
          % (G.Version, G.Version_cut))

    print("file_open")
    file_open(argv[1], G.fp_in, G.infile_name)
    file_open(argv[2], G.fp_out, G.outfile_name)

    print("dtst")
    dtst()

    G.fp_in[zisseki_hosei] = None

    print("econ")
    econ()

    G.fp_in[KEIZAI] = None
    G.fp_in[KAITEI] = None
    G.fp_in[TANNEN_CUT] = None

    print("read kokunen_jisseki")
    ReadKokunen_jisseki()

    for seido in range(KOUNEN, SHIGAKU + 1):
        # 癖 2. 出すだけ
        if seido == KOUNEN:
            print("read kounen")
        elif seido == KOKKYO:
            print("read kokkyo")
        elif seido == CHIKYO:
            print("read chikyo")
        elif seido == SHIGAKU:
            print("read shigaku")
        else:
            print("指定外の数字を検出しました")
            sys.exit(1)

        ReadHiyousha(seido)

    print("waku")
    waku()

    for seido in range(KOKUNEN_1GOU, SHIGAKU_3GOU + 1):
        G.fp_in[seido] = None

    print("tumatumi_cal_jisseki")
    tumatumi_cal_jisseki()

    print("給付水準調整前 給付費")
    Atamawari()

    print("read_flie")
    read_file()

    # [移植パッチ] `fclose( fp_in[0] )` は read_file.c が既に閉じている

    print("flie_write_kakyu")
    file_write_kakyu()

    print("printout")
    printout(0)

    print("カットファイル作成")

    if G.kako == 0:
        if G.CUT_KOTEI == 0:
            print("方式１（有限均衡・積立度合）")
            print("tyousei")
            tyousei()

            print("file_write")
            file_write_cut()

            G.fp_out[SETTEI].write("カット終了年度     %d\n" % G.S_C_NENDO)

        if G.CUT_KOTEI == 1:
            print("read_cut")
            read_cut()

            print("dokuzi_cal")
            dokuzi_cal()
    elif G.kako >= 1:
        print("過去債務推計")

        print("read_cut")
        read_cut()

        print("dokuzi_cal")
        dokuzi_cal()

    print("給付水準調整後 給付費")
    print("頭割り")
    Atamawari()

    print("printout")
    printout(1)

    G.fp_out[SETTEI].write("\n")        # 癖 4.

    print("end")

    # プロセス終了時のフラッシュに当たるもの（原本が閉じない分）
    for k, fp in enumerate(G.fp_out):
        if fp is not None:
            fp.close()
            G.fp_out[k] = None


def main():
    run(sys.argv)


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    main()
