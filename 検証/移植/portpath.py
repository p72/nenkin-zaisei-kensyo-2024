# -*- coding: utf-8 -*-
"""
システムごとにモジュール名が衝突するのを避ける
==============================================
移植版は**原本のファイル名をそのまま使う**方針なので、システムをまたぐと
同じ名前のモジュールがいくつも生まれる。

6システム分を並べた実測では、17個の名前がぶつかる。

    main.py        ⑤ ⑥ ① ④ ② ③   ← 6システム全部
    setconst.py    ⑤ ⑥ ① ④ ② ③   ← 6システム全部
    cntl.py        ⑤ ① ④ ② ③
    econ.py        ⑤ ④ ② ③
    glva.py        ⑤ ① ④ ② ③
    dtst.py        ④ ② ③
    waku.py        ④ ② ③
    cnum.py        ⑤ ① ④
    file_open.py   ④ ③
    flck.py        ⑤ ②
    fopn.py        ⑤ ①
    kiso.py        ② ③
    printout.py    ④ ③
    seid.py        ② ③
    shke.py        ② ③
    siml.py        ② ③
    stat.py        ② ③

（⑤ emp_shushi ⑥ bunpu ① hihokensha ④ kiso_nenkin ② emp_kyufu ③ nat）

`stat.py` だけは**標準ライブラリの `stat` ともぶつかる**。`os` が起動時に
読み込むので `sys.modules["stat"]` は必ず埋まっていて、`sys.path` の順では
解けない。②も③も importlib でファイルパスを指して読む（③は
`nat/natload.py` の `load_stat()`、②は `emp_kyufu/stat.py` の解説にある
手順を呼ぶ側が踏む）。標準の `stat` を `sys.modules` から外してはいけない
（`pathlib` や `tarfile` があとで掴んでしまう）。

各システムの中では素の `from setconst import …` で読み込むので、
`sys.path` にディレクトリを足すだけだと**先に読み込まれた別システムの
モジュールが `sys.modules` に残って取り違える**。

    ⑥のテストが bunpu/setconst.py を `setconst` として読み込む
    → ⑤のテストの emp_shushi/glva.py が `from setconst import ECEDY`
    → ImportError（bunpu の setconst に ECEDY は無い）

実際に踏んだ。`検証/移植` 全体を1回の pytest で回すと⑤の14件が落ちた。

対策
----
`select("emp_shushi")` のように**使うシステムを宣言する**と、

1. `sys.path` から他のシステムのディレクトリを外し、指定した順で先頭に置く
2. `sys.modules` から**他のシステムのディレクトリにあるモジュールを外す**

テスト側は

    SYSTEMS = ("emp_shushi",)          ← conftest.py が各テストの前に使う
    select(*SYSTEMS)                   ← 読み込み時（collection）にも効かせる

の2行を書く。`conftest.py` の `pytest_runtest_setup` が各テストの直前に
`select(*SYSTEMS)` を呼ぶので、フィクスチャの中で遅れて読み込む場合も
正しいディレクトリから取れる。

なぜ名前を変えないのか
----------------------
移植の読みやすさは「原本のどのファイルに対応するか」が一目で分かることに
かかっている。`setconst_emp.py` のように改名すると対応が崩れるので、
**名前は原本のまま**にして読み込み側で解決する。
"""
import os
import sys

__all__ = ["HERE", "SYSTEM_DIRS", "select"]

HERE = os.path.dirname(os.path.abspath(__file__))

# 同名モジュールを持ちうるディレクトリ。
# 移植したシステムを増やしたら**必ずここにも足す**。忘れると select() が
# `sys.path` からそのディレクトリを外さないので、後のテストに残り続ける。
SYSTEM_DIRS = ("emp_shushi", "bunpu", "hihokensha", "kiso_nenkin",
               "emp_kyufu", "nat", "clib")


def select(*dirs):
    """`dirs` のディレクトリだけを `sys.path` の先頭に置き、
    他のシステムから読み込んだモジュールを `sys.modules` から外す。

    `dirs` は探す順。`select("clib", "emp_shushi")` なら `clib` を先に見る。
    """
    paths = [os.path.join(HERE, d) for d in dirs]
    for d in SYSTEM_DIRS:
        p = os.path.join(HERE, d)
        while p in sys.path:
            sys.path.remove(p)
    for p in reversed(paths):
        sys.path.insert(0, p)

    keep = set(paths)
    for name, mod in list(sys.modules.items()):
        f = getattr(mod, "__file__", None)
        if not f:
            continue
        d = os.path.dirname(os.path.abspath(f))
        # 移植版のディレクトリの中で、今回使わないものだけ外す。
        # `検証/移植` 直下（テスト本体と このファイル）は残す
        if d != HERE and d.startswith(HERE + os.sep) and d not in keep:
            del sys.modules[name]
