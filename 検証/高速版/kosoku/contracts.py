# -*- coding: utf-8 -*-
"""段階間のデータ契約 — in-memory のデータセットと来歴
=====================================================
5段階（①外枠 → ②給付費 → ③国民年金 → ④基礎年金 → ⑤収支）は、それぞれ
frozen dataclass を返す。配列は `axis.py` の軸で添字を切る。

来歴（`Provenance`）は「どのケースを、どの policy で、どの段階が、いつ、
何から作ったか」を持ち、`source` が `fast`（高速版が計算した）か
`port_csv`（移植版の CSV を読んだ）かを区別する。フェーズごとに上流を
移植版の CSV から高速版に切り替えるとき、ドリフトを段階に帰属させるため。

配列の中身の意味（列・軸）は各段階の docstring に書く。フェーズ 0 では
型だけを置く。
"""
from dataclasses import dataclass, field
import datetime as _dt
import hashlib
import json
import subprocess

import numpy as np

__all__ = ["Provenance", "SEXES", "Waku", "KyufuOut", "NatOut", "KisoOut", "ShushiOut",
           "policy_hash", "git_rev"]


def policy_hash(policy_dict):
    """policy（yaml を dict にしたもの）の内容ハッシュ。順序に依らない。"""
    s = json.dumps(policy_dict, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]


def git_rev(cwd=None):
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=cwd,
                              capture_output=True, text=True, timeout=5
                              ).stdout.strip() or "unknown"
    except Exception:                    # pragma: no cover - git 無し
        return "unknown"


@dataclass(frozen=True)
class Provenance:
    case: str                  # 例 "3001"（試算番号-経済前提-外枠を1つの文字列で）
    stage: str                 # "s1" … "s5"
    source: str                # "fast" | "port_csv"
    policy: str = ""           # policy_hash()
    rev: str = ""              # git rev
    created: str = field(default_factory=lambda: _dt.datetime.now().isoformat(timespec="seconds"))
    upstream: tuple = ()       # 上流の Provenance（段階順）
    note: str = ""

    def chain(self):
        """上流から順に並べた (stage, source) の列。"""
        return tuple((p.stage, p.source) for p in self.upstream) + ((self.stage, self.source),)


def _check(arr, name, ndim=None):
    if not isinstance(arr, np.ndarray):
        raise TypeError("%s は ndarray でなければならない" % name)
    if ndim is not None and arr.ndim != ndim:
        raise ValueError("%s の次元は %d でなければならない（%d）" % (name, ndim, arr.ndim))


SEXES = ("男女計", "男", "女", "女有配偶", "女無配偶")     # ①の性の軸（港の sei 0〜4）


@dataclass(frozen=True)
class Waku:
    """①外枠の出力。被保険者数の外枠（分類 × 年度 × 性 × 年齢）と調整率。

    `count[c, y, s, x]`: 分類 c（`classes`。港の `waku-00..57` の順）・年度 y（`YEARS`）・性 s
    （`SEXES`）・年齢 x（`AGES`。101 歳以上は 100 歳に寄せてある）の人数。
    `cutritu[y]`: マクロ経済スライドの調整率（港の `waku-m`。`1 / 率 − 1` を小数 4 桁に丸めた値）。
    """
    prov: Provenance
    classes: tuple
    count: np.ndarray            # (len(classes), YEARS.n, len(SEXES), AGES.n)
    cutritu: np.ndarray          # (YEARS.n,)
    sexes: tuple = SEXES

    def __post_init__(self):
        _check(self.count, "count", 4)
        _check(self.cutritu, "cutritu", 1)


@dataclass(frozen=True)
class KyufuOut:
    """②厚生年金給付費推計の出力（制度ごと）。

    `kiso[...]`: ④へ渡す基礎年金の系列、`shus[...]`: ⑤へ渡す収支の系列。
    列の意味はフェーズ D で確定する。`kaite`: 改定率（年度 × 年齢）。
    """
    prov: Provenance
    system: str                  # "kou" | "kok" | "ren" | "sig"
    kiso: dict = field(default_factory=dict)
    shus: dict = field(default_factory=dict)
    kaite: dict = field(default_factory=dict)


@dataclass(frozen=True)
class NatOut:
    """③国民年金の出力。

    `kisonenkin`: ④へ渡す基礎年金の系列（給付ごと・年度 × 年齢）。
    `dokuzi`: 独自給付。`kokukaite`: 国民年金の改定率（年度 × 年齢）。
    """
    prov: Provenance
    kisonenkin: dict = field(default_factory=dict)
    dokuzi: dict = field(default_factory=dict)
    kokukaite: np.ndarray = None


@dataclass(frozen=True)
class KisoOut:
    """④基礎年金の出力。

    `kyoshutukin`: 拠出金の直積（タグ → 年度）。`cuta`: マクロ経済スライドの
    累積調整率（年度 × 年齢）。`kekka`: 30列の財政見通し（列名 → 年度）。
    `tumatumi`: 積立金の見通し。`owari`: 調整終了年度。
    """
    prov: Provenance
    kyoshutukin: dict = field(default_factory=dict)
    cuta: np.ndarray = None
    kekka: dict = field(default_factory=dict)
    tumatumi: dict = field(default_factory=dict)
    owari: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ShushiOut:
    """⑤厚生年金収支計算の出力。

    `shushi[制度][列名]`: 年度の配列（`01shushi` の30列 × 5制度）。
    `summary[列名]`: `03summary`（所得代替率・モデル年金額）。
    `owari`: 調整終了年度（厚年・国年）。`final_rate`: 最終所得代替率
    （計・比例・基礎）。
    """
    prov: Provenance
    shushi: dict = field(default_factory=dict)
    summary: dict = field(default_factory=dict)
    owari: dict = field(default_factory=dict)
    final_rate: dict = field(default_factory=dict)
