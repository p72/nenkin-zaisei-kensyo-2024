# -*- coding: utf-8 -*-
"""制度の型 — frozen dataclass
==============================
データとコードの線引き（`計画.md`「制度のデータ化」）:

- **データ**: 法令の出典か制度改正年度を持つ値、および (年度|生年度|年齢|性|制度)
  による表引き。ここに型を置く
- **コード**: 算術・漸化式・解法。`stages/` と `kernels/` に置く

yaml の各値は `{value: …, source: "file:line"}` の形で書く（`load.py` が
`value` を取り出し、`source` は `Policy.sources` に集める）。値だけの
書き方も許すが、`tests/test_policy_seed.py` は `source:` の無い項目を
数えて報告する。

`Schedule` は表引きの共通形。`by: year|cohort|age` と `points`（キー→値、
キーは昇順）で、キー未満は最初の値、以降は「その点以降の値」（階段）。
"""
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Tuple

import numpy as np

__all__ = ["Schedule", "Rounding", "Policy"]


@dataclass(frozen=True)
class Schedule:
    """階段状の表引き。`points` は (キー, 値) の昇順の組。"""
    by: str                       # "year" | "cohort" | "age"
    points: Tuple[Tuple[int, Any], ...]

    def __post_init__(self):
        keys = [k for k, _ in self.points]
        if keys != sorted(keys) or len(set(keys)) != len(keys):
            raise ValueError("Schedule(%s): キーは昇順で重複なし" % self.by)
        if not keys:
            raise ValueError("Schedule(%s): 点が無い" % self.by)

    def at(self, key):
        """キーに対する値。最初の点より前は最初の値。"""
        v = self.points[0][1]
        for k, val in self.points:
            if key >= k:
                v = val
            else:
                break
        return v

    def array(self, keys):
        """キーの配列に対する値の配列（数値のとき）。"""
        keys = np.asarray(keys)
        out = np.empty(keys.shape, dtype=np.float64)
        flat = out.reshape(-1)
        for i, k in enumerate(keys.reshape(-1)):
            flat[i] = self.at(int(k))
        return out

    @classmethod
    def from_mapping(cls, by, mapping):
        return cls(by, tuple(sorted((int(k), v) for k, v in mapping.items())))


@dataclass(frozen=True)
class Rounding:
    """法定の丸め。`unit` の倍数に `mode` で丸める。

    mode: "nearest"（四捨五入）| "down"（切り捨て）| "up"（切り上げ）
    """
    unit: float
    mode: str = "nearest"

    def apply(self, x):
        x = np.asarray(x, dtype=np.float64)
        q = x / self.unit
        if self.mode == "nearest":
            r = np.floor(q + 0.5)
        elif self.mode == "down":
            r = np.floor(q)
        elif self.mode == "up":
            r = np.ceil(q)
        else:
            raise ValueError("Rounding: mode %r" % self.mode)
        return r * self.unit


@dataclass(frozen=True)
class Policy:
    """読み込んだ制度。`data` は値だけの入れ子 dict、`sources` は
    key path（"kiso.mangaku.2024" のようなドット区切り）→ `source:`。

    型付きのアクセスはフェーズ A 以降で系統ごとに足す（`KisoPolicy` 等）。
    フェーズ 0 では `get("kounen.hokenryoritu.cap")` の形で引く。
    """
    data: Mapping[str, Any]
    sources: Mapping[str, str] = field(default_factory=dict)
    origin: Tuple[str, ...] = ()          # 読み込んだ yaml の並び

    def get(self, path, default=KeyError):
        cur = self.data
        for part in path.split("."):
            if isinstance(cur, Mapping) and part in cur:
                cur = cur[part]
            else:
                if default is KeyError:
                    raise KeyError(path)
                return default
        return cur

    def schedule(self, path):
        """`{by: …, points: {k: v}}` の項を `Schedule` に。"""
        node = self.get(path)
        return Schedule.from_mapping(node["by"], node["points"])

    def rounding(self, path):
        node = self.get(path)
        return Rounding(float(node["unit"]), node.get("mode", "nearest"))

    def source(self, path):
        return self.sources.get(path, "")

    def unsourced(self):
        """`source:` の無い葉の key path の一覧。"""
        out = []

        def walk(node, prefix):
            if isinstance(node, Mapping):
                for k, v in node.items():
                    walk(v, prefix + (str(k),))
            else:
                p = ".".join(prefix)
                if p not in self.sources:
                    out.append(p)
        walk(self.data, ())
        return out
