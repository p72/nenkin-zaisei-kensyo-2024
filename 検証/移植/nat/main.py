# -*- coding: utf-8 -*-
"""
国民年金/main.c の忠実移植（③の入口）
=====================================
130 行。呼ぶ順を決めるだけ。

```c
cntl( argc , argv );
file_open( argv[1] , fp_in  , infile_name );
file_open( argv[2] , fp_out , outfile_name );
seid();  econ();  waku();  kaizen();  noufuritu();

for( shubetu = 1 ; shubetu <= MAX_SHUBETU - 1 ; shubetu++ )
    if( PerformSiml( shubetu ) )          /* 2・3・5・6 だけ真 */
    {
        dtst( shubetu );
        kiso( shubetu );
        shke( SUIKEISHONENDO , shubetu );
        for( nendo = SUIKEISHONENDO + 1 ; nendo <= SUIKEISAISHUNENDO ; nendo++ )
        { siml( nendo , shubetu ); shke( nendo , shubetu ); }
    }

stat();
printout();
```

種別を **2 → 3 → 5 → 6** の順に回し、**1つの種別を 105年ぶん
回し切ってから次の種別に移る**。これが大事な点で、

- `kiso()` の遺族の発生割合は種別 3 で埋め直されないので、
  種別 2 が読んだ値が種別 3 の推計に使われる（`検証/原本の不具合.md`
  **F24**）
- `siml()` の `static` な局所配列は呼び出しをまたいで残る
- `printout()` の `sotai_nendo - 1` が -1 になる読みは
  「1つ前の種別の最終年度」を読む（同 **B12**）

**順番を変えると結果が変わる。**

`zero()` と `file_close()` は宣言だけで定義が無い
-------------------------------------------------
`snaps.h` が宣言しているが 16本の .c のどこにも定義が無く、
`main.c` も呼ばない（同 **F23**）。移植版は `file_close()` を
中身のある関数として書いた（Python は参照が切れるまで閉じない）。

`stat` の名前が標準ライブラリとぶつかる
--------------------------------------
`nat/stat.py` は `import stat` では読めない。`natload.load_stat()`
を通す（`nat/natload.py` の解説を参照）。
"""
import sys

import cntl as _cntl
import dtst as _dtst
import econ as _econ
import file_open as _fo
import kaizen as _kaizen
import kiso as _kiso
import noufuritu as _noufuritu
import printout as _printout
import seid as _seid
import shke as _shke
import siml as _siml
import waku as _waku
from glva import G
from natload import load_stat
from setconst import MAX_SHUBETU, SUIKEISAISHUNENDO, SUIKEISHONENDO

__all__ = ["main", "PerformSiml"]


def PerformSiml(shubetu):
    """main.c:113 の忠実移植。推計する種別かどうか。"""
    return 1 if shubetu in (2, 3, 5, 6) else 0


_NAME = {2: "１号男子推計", 3: "３号男子推計",
         5: "１号女子推計", 6: "３号女子推計"}


def main(argv, asctime=None, echo=True, years=None):
    """main.c:24 の忠実移植。

    `argv` は原本と同じ並び（`argv[0]` はプログラム名）。
    `asctime` は `write_BeginData()` に渡す実行時刻（突き合わせの
    ときだけ固定する）。`years` を渡すと `siml` を回す年数を
    縮められる（テスト用。既定は原本どおり 2125年度まで）。
    """
    def say(s):
        if echo:
            print(s)
            sys.stdout.flush()

    say("start")

    say("cntl")
    _cntl.cntl(G, argv)

    print("The version number of this run is %s." % G.Version)

    say("file open")
    _fo.file_open(G, argv[1], G.fp_in, G.infile_name)
    _fo.file_open(G, argv[2], G.fp_out, G.outfile_name)

    say("seid")
    _seid.seid(G)

    say("econ")
    _econ.econ(G)

    say("waku")
    _waku.waku(G)

    say("kaizen")
    _kaizen.kaizen(G)

    say("noufuritu")
    _noufuritu.noufuritu(G)

    saishu = SUIKEISAISHUNENDO if years is None \
        else SUIKEISHONENDO + years

    for shubetu in range(1, MAX_SHUBETU):
        if not PerformSiml(shubetu):
            continue

        say(_NAME[shubetu])

        say("dtst")
        _dtst.dtst(G, shubetu)

        say("kiso")
        _kiso.kiso(G, shubetu)

        say("shke・siml")
        _shke.shke(G, SUIKEISHONENDO, shubetu)

        for nendo in range(SUIKEISHONENDO + 1, saishu + 1):
            _siml.siml(G, nendo, shubetu)
            _shke.shke(G, nendo, shubetu)

    say("stat")
    load_stat().stat(G, asctime=asctime)

    say("printout")
    _printout.printout(G)

    say("end")

    _fo.file_close(G)


if __name__ == "__main__":
    main([None] + sys.argv[1:])
