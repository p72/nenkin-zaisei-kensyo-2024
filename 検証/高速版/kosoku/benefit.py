# -*- coding: utf-8 -*-
"""給付の共通の型 — BenefitSpec / InsuredClass / BenefitModel / 登録簿
====================================================================
移植版③は9つの構造体 × 給付ごとにコードが並び、②は `i = 1..13` の給付を
三重ループで回す。高速版は「給付とは何か」を `BenefitSpec`（データ）と
`BenefitModel`（ライフサイクル）に分け、**新規発生 `shinki()` だけ**を
給付ごとに書く。年度末・年度間・カット・集計・出力は既定の実装で動く。

新しい給付種別を足す手順は `計画.md`「新しい給付種別を足す」。

フェーズ 0 では型と登録簿だけ。既定のライフサイクルの実装はフェーズ A（③）で
`algebra.py` の上に書く。
"""
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from .algebra import Layout

__all__ = ["AgeRule", "KisoTag", "InsuredClass", "BenefitSpec", "Registry"]


@dataclass(frozen=True)
class AgeRule:
    """受給年齢の範囲と、新規裁定が起きる年齢の扱い。"""
    min_age: int
    max_age: int
    start: str = "fixed"        # "fixed"（min_age で裁定）| "kuriage"（繰上げ・繰下げの区分あり）


@dataclass(frozen=True)
class KisoTag:
    """④基礎年金の直積のマス（制度, 新旧, 区分, 対象, 形態）。"""
    seido: str
    shinkyu: str
    kubun: str
    taisho: str
    keitai: str


@dataclass(frozen=True)
class InsuredClass:
    """被保険者の区分。③の `shubetu` 2,3,5,6、②の制度、⑤の ii=1..4 を名前で持つ。
    **計は計算で出す**（魔法の添字にしない）。"""
    name: str
    sex: str                    # "male" | "female"
    system: str                 # "kokunen" | "kou" | "kok" | "ren" | "sig"
    gou: int                    # 1 | 2 | 3（被保険者の号）
    waku_column: Optional[int] = None    # ①の58分類のどれが外枠か
    transition: str = "kokunen"          # 状態遷移の型（仕様 §4.2 か §4.3）
    contributes: bool = True
    kyoshutu_taisho: bool = True
    premium: str = "monthly"             # "monthly"（定額）| "rate"（報酬比例）


@dataclass(frozen=True)
class BenefitSpec:
    """給付種別の仕様（データ）。"""
    name: str
    system: str                          # "kokunen" | "kounen"
    layout: Layout                       # 額の欄の並び（`algebra.Layout`）
    age: AgeRule
    classes: Tuple[str, ...]             # 適用する InsuredClass の名前
    extra_axes: Tuple[Tuple[str, int], ...] = ()   # (("jukyu_nenrei", 11),) など
    kiso_tag: Optional[KisoTag] = None   # ④の直積のマス
    shushi_col: Optional[str] = None     # ⑤の収支の列名（etoc の置き換え）
    rounding: Dict[str, str] = field(default_factory=dict)   # 欄 → policy の rounding の key path
    spec_ref: str = ""                   # 仕様書の節
    port_ref: str = ""                   # 移植版の関数（dir/file.py:func）


class Registry:
    """給付の登録簿。名前で引く。段階（③②）ごとに1つ持つ。"""

    def __init__(self):
        self._specs: Dict[str, BenefitSpec] = {}
        self._models: Dict[str, object] = {}

    def add(self, spec, model=None):
        if spec.name in self._specs:
            raise KeyError("給付 %s は登録済み" % spec.name)
        self._specs[spec.name] = spec
        if model is not None:
            self._models[spec.name] = model
        return spec

    def spec(self, name):
        return self._specs[name]

    def model(self, name):
        return self._models[name]

    def __iter__(self):
        return iter(self._specs.values())

    def __len__(self):
        return len(self._specs)

    def names(self):
        return tuple(self._specs)
