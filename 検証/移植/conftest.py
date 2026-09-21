# -*- coding: utf-8 -*-
"""
pytest の設定。テストごとにシステムのモジュールを選び直す
========================================================
各テストモジュールが `SYSTEMS = ("emp_shushi",)` のように使うシステムを
宣言する。ここでテストの直前に `portpath.select(*SYSTEMS)` を呼んで、
`sys.path` と `sys.modules` を宣言どおりに揃える。

理由は `portpath.py` の解説を参照（原本のファイル名をそのまま使うので、
システムをまたぐと `setconst.py` などが衝突する）。
"""
import portpath


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "slow: 時間のかかるテスト（C と Python を丸ごと走らせる）")


def pytest_runtest_setup(item):
    dirs = getattr(item.module, "SYSTEMS", None)
    if dirs:
        portpath.select(*dirs)
