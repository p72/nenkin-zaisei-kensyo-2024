# -*- coding: utf-8 -*-
"""
厚生年金/給付費推計/sepsd.cpp の忠実移植（1制度ぶんの推計を通す）
===================================================================
129 行。②の**骨**。`main()` が制度（`pseid`）ごとに1回呼ぶ。

    fopn()   入出力を開く
    flck()   入力の来歴を出力に写し、読む位置をデータの先頭に合わせる
    waku()   外枠（①被保険者推計の結果）を読む
    econ()   経済前提と改定率
    seid()   制度の定数と支給率
    krgn()   繰上げ・繰下げの率

    for s in 1..3:                      種別（1 男 / 2 女 / 3 第3号）
        kiso()                          基礎率（この s のぶん）
        k = KIJUN; dtst()               足元（2021年度）の基礎数
        shke()                          2021年度の集計
        for k in KIJUN+1..KE:           2022〜2125年度
            siml(); shke()

    outkn()    国庫負担の内訳            （`key` が 11・12・13）
    rousaki()  老齢先充てへの振り替え    （`flg_toukei == 0`）
    pstat()    足元の確認用ファイル      （`key` が 11・13）
    stat()     年度間の平均と「計」
    crshfl()   ⑤⑥が読むファイルを書く
    outhou()   報酬の内訳（確認用）      （`key == 11`）
    fcls()     閉じる

`s` のループの抜け方
--------------------
```c
GLOBAL_FOR(s, 1, 3) {
  if(pseid != 0 && s >= 3) break;
  if(s <= 3) s2 = s;
```

第3号被保険者（`s = 3`）があるのは厚生年金だけなので、共済は
`s = 3` に入る前に抜ける。`if(s <= 3)` は `s` が 1〜3 なので**常に真**
（F17 の仲間）。`s2` は「基礎率を引くときの種別」で、`s` と同じ値を
持つが `shkejken` などが `s` を局所変数で隠す場所があるため
別に持っている。

`xend` と `tend`
----------------
```c
k = KIJUN;
if(pseid == 0) { xend = 90; } else { xend = 75; }
tend = xend - 15;
```

`xend` は被保険者を追う年齢の上限（厚年 90 / 共済 75）、`tend` は
加入からの経過年の上限。**`s` のループの中で毎回入れ直す**が
値は変わらない。

`FILE *fp = fp_map["prog"]` は `-DDEBUG` のときだけ使う
-------------------------------------------------------
```c
FILE *fp = fp_map["prog"];

#ifdef DEBUG
fprintf(fp, "[kiso] pseid = %d, s = %d\\n", pseid, s);
#endif
```

`fp` を取るところは `#ifdef` の外、使うところは中。同梱の
Makefile の `release` は `-O2` だけで `-DDEBUG` を付けないので、
**`PROG.log` は開くだけで1バイトも書かれない**。
`make debug OP=-DDEBUG` で建てたときだけ進捗が入る。
移植版も同じで、`PROG.log` は空のまま作る。

例外が出たら閉じてから投げ直す
------------------------------
```c
catch (const std::exception &ex) {
  clog << ex.what() << "\\n";
  clog << "推計中に例外が発生したので開いているファイルを閉じます。\\n";
  fcls();
  throw;
}
catch (...) { … fcls(); throw; }
```

移植版は `try` / `except BaseException` で同じことをする。
`std::exception` と `...` の2つに分かれているのは、前者だけ
`ex.what()` を出すため。
"""
import sys

from setconst import KE, KIJUN

import crshfl as _crshfl
import dtst as _dtst
import econ as _econ
import fileio as _fileio
import flck as _flck
import kiso as _kiso
import krgn as _krgn
import outhou as _outhou
import outkn as _outkn
import pstat as _pstat
import rousaki as _rousaki
import shke as _shke
import seid as _seid
import siml as _siml
import waku as _waku
from glva import G

# `stat` は Python 標準ライブラリと名前がぶつかる。`os` が起動時に
# 読み込むので `sys.modules["stat"]` は必ず埋まっていて、素の
# `import stat` では標準の方を取ってしまう。原本のファイル名を
# 変えない方針なので、ファイルを指して読み込む。
# `sys.modules["stat"]` を**外してはいけない**（`pathlib` や
# `tarfile` があとで `import stat` したときにこちらを掴む）。
import importlib.util as _ilu
import os.path as _op

_STAT_PATH = _op.join(_op.dirname(_op.abspath(__file__)), "stat.py")
_spec = _ilu.spec_from_file_location("emp_kyufu_stat", _STAT_PATH)
_stat = _ilu.module_from_spec(_spec)
sys.modules["emp_kyufu_stat"] = _stat
_spec.loader.exec_module(_stat)

__all__ = ["sepsd"]


def sepsd():
    """sepsd.cpp:9 void seps::sepsd(void) の忠実移植。"""
    try:
        _fileio.fopn()
        print("fopn 終了")

        _flck.flck()
        print("flck 終了")

        _waku.waku()
        print("waku 終了")

        _econ.econ()
        print("econ 終了")

        _seid.seid()
        print("seid 終了")

        _krgn.krgn()
        print("krgn 終了")

        print("種別についてのループを実行します（s: 0 -> 3）")
        # `#ifdef DEBUG` のときだけ「PROG.log に出す」という案内が入る

        # `fp` は `-DDEBUG` のときだけ使う（開いてあることの確かめ）
        assert "prog" in G.fp_map

        for s in range(1, 3 + 1):
            G.s = s                     # 原本は GLOBAL_FOR（グローバルの s）
            if G.pseid != 0 and s >= 3:
                break

            if s <= 3:                  # 常に真（F17 の仲間）
                G.s2 = s

            _kiso.kiso()

            G.k = KIJUN

            if G.pseid == 0:
                G.xend = 90
            else:
                G.xend = 75
            G.tend = G.xend - 15

            if s <= 3:                  # 常に真
                _dtst.dtst()

            _shke.shke()

            print("(pseid, s) = (%d, %d) 推計中" % (G.pseid, s))

            for k in range(KIJUN + 1, KE + 1):
                G.k = k                 # 原本は GLOBAL_FOR（グローバルの k）
                _siml.siml()
                _shke.shke()

        if G.key == 11 or G.key == 12 or G.key == 13:
            _outkn.outkn()
            print("outkn 終了")

        if G.flg_toukei == 0:
            _rousaki.rousaki()
            print("rousaki 終了")

        if G.key == 11 or G.key == 13:
            _pstat.pstat()
            print("pstat 終了")

        _stat.stat()
        print("stat 終了")

        _crshfl.crshfl()
        print("crshfl 終了")

        if G.key == 11:
            _outhou.outhou()
            print("outhou 終了")

        _fileio.fcls()
        print("fcls 終了")

    except BaseException as ex:
        # 原本は std::exception と ... の2つに分ける。前者だけ what() を出す
        if isinstance(ex, Exception):
            print(ex, file=sys.stderr)
        print("推計中に例外が発生したので開いているファイルを閉じます。",
              file=sys.stderr)
        _fileio.fcls()
        raise
