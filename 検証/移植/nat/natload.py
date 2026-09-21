# -*- coding: utf-8 -*-
"""名前が標準ライブラリとぶつかるモジュールの読み込み口。

`国民年金/stat.c` の移植は `nat/stat.py` だが、`import stat` では
**標準ライブラリの `stat`** が返る。`os` が起動時に読み込むので
`sys.modules["stat"]` は必ず埋まっていて、消すと `pathlib` や
`tarfile` が壊れる。②の `emp_kyufu/stat.py` と同じ作りにした。

    from natload import load_stat
    stat_mod = load_stat()
    stat_mod.stat(G)
"""
import importlib.util as _ilu
import os.path as _op
import sys

__all__ = ["load_stat"]

_HERE = _op.dirname(_op.abspath(__file__))


def load_stat():
    """`nat/stat.py` を `nat_stat` という名前で読む（1回だけ）。"""
    got = sys.modules.get("nat_stat")
    if got is not None:
        return got
    spec = _ilu.spec_from_file_location("nat_stat",
                                        _op.join(_HERE, "stat.py"))
    mod = _ilu.module_from_spec(spec)
    sys.modules["nat_stat"] = mod
    spec.loader.exec_module(mod)
    return mod
