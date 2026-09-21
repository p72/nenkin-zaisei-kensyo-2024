# -*- coding: utf-8 -*-
"""
C の `scanf` を模す（⑤で検証済みの実装を使い回す）
==================================================
①被保険者推計も⑤と同じ `scanf("%d%*c", &x)` で標準入力から設定を読む。
⑤の `emp_shushi/cscan.py` がそのまま使えるので、**同じものを2つ持たない**
ようにここから読み込む。

`clib/libc.py` と同じ理由で `sys.path` はいじらない。⑤（`emp_shushi/`）と
①（`hihokensha/`）には `cnum.py` のように**同じ名前のモジュール**が
あるので、`sys.path` に両方を入れると取り違える。
"""
import importlib.util
import os

_SRC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "emp_shushi", "cscan.py")

_spec = importlib.util.spec_from_file_location("_emp_cscan", _SRC)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

Scan = _mod.Scan

__all__ = ["Scan"]
