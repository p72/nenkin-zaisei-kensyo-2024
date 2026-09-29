# -*- coding: utf-8 -*-
"""③国民年金（フェーズ A）
=========================
被保険者の状態遷移（§4.2）、納付率、給付の新規発生・年度末・年度間（§5.1〜5.3）、
集計と④への受け渡し（`KISONENKIN` 相当）。

構成
----
    layouts.py     給付ごとの欄の並び（`algebra.Layout`）
    inputs.py      基礎率・足元・外枠の読み手（移植版③の入力86本のうち使うもの）
    transition.py  被保険者・待期者の1年の遷移
    benefits.py    給付の新規発生と年度末（登録簿）
    aggregate.py   受給者数・年金額の年齢階級別の集計（shke 相当）
    run.py         年度ループと `NatOut` の組み立て

港: nat/main.py:main
仕様: §4.2、§5.1〜5.3、§5.7
"""
from .run import run as run_nat, read_inputs, CLASSES   # noqa: F401（`run` はモジュール名）
