# -*- coding: utf-8 -*-
"""玩具ケース（計画 §I）— 勘定 2 つ・流れ 1 本の台帳で `statement` `identities` `merge` を手計算と合わせる
===========================================================================================================
勘定 A（厚年役）と B（共済役）。年度は添字 0〜3（0 が基準年度）。

    A: 保険料 100、運用 5、国庫 20、支援出 10、独自給付 60、拠出金 40、事務費 3   → 収入計 125、支出計 113、収支差 12
    B: 保険料 30、運用 1、国庫 5、支援入 10、独自給付 20、拠出金 15、事務費 1     → 収入計 46、支出計 36、収支差 10
    流れ shien: A → B 10。統合すると消え、統合勘定の収入計 = 125 + 46 − 10 = 161、支出計 = 113 + 36 − 10 = 139
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from conftest import FAST                                     # noqa: E402,F401

from kosoku.axis import YEARS                                 # noqa: E402
from kosoku.accounts import Account, Transfer, Ledger, identities, merge, statement   # noqa: E402


def _acc(name, **v):
    n = YEARS.n
    f = {k: np.zeros(n) for k in ("保険料", "運用収入", "国庫負担", "支援入", "納付金", "妻積",
                                    "独自給付", "基礎年金拠出金", "事務費", "支援出", "国庫負担(基礎)")}
    for k, x in v.items():
        f[k][1:4] = x
    inn = sum(f[k] for k in ("保険料", "運用収入", "国庫負担", "支援入", "納付金", "妻積"))
    out = sum(f[k] for k in ("独自給付", "基礎年金拠出金", "事務費", "支援出"))
    fund = np.zeros(n)
    fund[0] = 1000.
    for i in range(1, 4):
        fund[i] = fund[i - 1] + inn[i] - out[i]
    return Account(name, "employee", f, fund, inn, out)


def _ledger():
    A = _acc("A", 保険料=100., 運用収入=5., 国庫負担=20., 支援出=10., 独自給付=60., 基礎年金拠出金=40., 事務費=3.)
    B = _acc("B", 保険料=30., 運用収入=1., 国庫負担=5., 支援入=10., 独自給付=20., 基礎年金拠出金=15., 事務費=1.)
    t = Transfer("shien", ("A",), ("B",), "shien", {"A": A.flows["支援出"], "B": B.flows["支援入"]})
    return Ledger({"A": A, "B": B}, {"shien": t}, (YEARS.label(1), YEARS.label(3)))


def test_手計算の収支():
    L = _ledger()
    sa, sb = statement(L.accounts["A"]), statement(L.accounts["B"])
    assert sa["収入計"][1] == 125. and sa["支出計"][1] == 113. and sa["収支差"][1] == 12.
    assert sb["収入計"][1] == 46. and sb["支出計"][1] == 36. and sb["収支差"][1] == 10.
    assert sa["積立金"][3] == 1000. + 3 * 12.
    assert all(ok for _, _, ok in identities(L))


def test_統合で内部の流れが消える():
    L = _ledger()
    M = merge(L, ["A", "B"], "AB")
    a = M.accounts["AB"]
    s = statement(a)
    assert s["収入計"][1] == 161. and s["支出計"][1] == 139. and s["収支差"][1] == 22.
    assert a.flows["支援入"][1] == 0. and a.flows["支援出"][1] == 0.
    assert s["積立金"][3] == 2000. + 3 * 22.
    assert "shien" not in M.transfers
    assert all(ok for _, _, ok in identities(M)), identities(M)


def test_壊れた台帳は恒等式で見つかる():
    L = _ledger()
    L.accounts["A"].shunyu[2] += 1.                          # 収入計だけ 1 円ずらす
    bad = [n for n, _, ok in identities(L) if not ok]
    assert bad == ["A 収入計 = 部分和"]
