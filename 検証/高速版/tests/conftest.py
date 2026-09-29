# -*- coding: utf-8 -*-
"""高速版のテストの共通設定。

- `kosoku` を import できるように `検証/高速版/` を `sys.path` に置く
- 移植版を読むテストは `portpath.select()` を使うので `検証/移植/` も置く。
  移植版は**読み取り専用**（高速版は移植版に触らない）
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FAST = os.path.dirname(HERE)
PORT = os.path.normpath(os.path.join(FAST, "..", "移植"))

for p in (FAST, PORT):
    if p not in sys.path:
        sys.path.insert(0, p)
