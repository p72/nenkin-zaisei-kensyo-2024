# -*- coding: utf-8 -*-
"""④基礎年金（フェーズ B）
=========================
③国民年金と②厚生年金給付費推計が出した基礎年金の受給者数（年金額）を集め、
給付費を組み立てて被保険者数で頭割りし（拠出金）、国民年金の積立金が
2120年度に1年分の支出を残すようにマクロ経済スライドの終了年度を解く。

構成
----
    inputs.py   受給者数（③ KISONENKIN・② kiso.*）、外枠、実績の読み手
    econ.py     経済前提 → 改定率・調整率（pre_cut / T）・累積調整率
    kyufu.py    給付費の直積（制度×年齢×新旧×区分×対象×形態）と拠出金の頭割り
    dokuzi.py   独自給付（死亡一時金・寡婦・付加）と保険料・業務勘定
    tyousei.py  積立金の漸化式と終了年度の解法（年度走査 ＋ 二分法）
    output.py   受け渡し（KYOSHUTUKIN・cuta・TUMATUMI・kekka・provide）の書き手
    run.py      通し

港: kiso_nenkin/main.py:run
仕様: §6、§8.1〜8.4
"""
from .run import run as run_kiso, read_inputs   # noqa: F401（`run` はモジュール名）
