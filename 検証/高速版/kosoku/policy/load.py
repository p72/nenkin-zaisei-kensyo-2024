# -*- coding: utf-8 -*-
"""yaml の読み手 — `{value, source}` の畳み込みと overlay の merge
==================================================================
- 葉は `{value: …, source: "file:line"}` か、値そのもの
- `source:` は `Policy.sources[key path]` に集める
- `load_policy(base, *overlays)`: overlay は key path で merge する
  （dict は再帰的に、それ以外は置き換え）。**overlay に base に無いキーが
  あればエラー**（レバーのつもりの綴り違いを黙って通さない）。
  新しいキーを足すのは base に書く
"""
import os
from typing import Any, Dict

import yaml

from .model import Policy

__all__ = ["load_policy", "BASE_YAML", "OPTIONS_DIR", "fold"]

HERE = os.path.dirname(os.path.abspath(__file__))
BASE_YAML = os.path.join(HERE, "base_2024.yaml")
OPTIONS_DIR = os.path.join(HERE, "options")

# 葉に書けるキー。`match`/`port` は `tests/test_policy_seed.py` が移植版と照合するときの手掛かり
_LEAF_KEYS = {"value", "source", "note", "match", "port"}
# 構造を表すキー（表引きの `by:` など）。値ではないので `source:` は要らない
_STRUCT_KEYS = {"by"}


def _is_leaf(node):
    return isinstance(node, dict) and "value" in node and set(node) <= _LEAF_KEYS


def fold(node, prefix, sources):
    """`{value, source}` を値に畳み、`source` を集める。"""
    if _is_leaf(node):
        src = str(node["source"]) if node.get("source") else None
        if src:
            sources[".".join(prefix)] = src
        v = node["value"]
        if isinstance(v, dict):
            # 値が mapping の葉（`{unit, mode}` など）。中の項目にも同じ出典を付ける
            v = fold(v, prefix, sources)
            if src:
                _register(v, prefix, src, sources)
        return v
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            k = str(k)
            if k in _STRUCT_KEYS and not isinstance(v, dict):
                sources[".".join(prefix + (k,))] = "(構造)"
            out[k] = fold(v, prefix + (k,), sources)
        return out
    if isinstance(node, list):
        return [fold(v, prefix + (str(i),), sources) for i, v in enumerate(node)]
    return node


def _register(node, prefix, src, sources):
    """`node` の下の全 key path に出典 `src` を付ける（既にあれば残す）。"""
    if isinstance(node, dict):
        for k, v in node.items():
            _register(v, prefix + (str(k),), src, sources)
    else:
        sources.setdefault(".".join(prefix), src)


def _merge(base, over, path):
    if isinstance(base, dict) and isinstance(over, dict):
        out = dict(base)
        for k, v in over.items():
            k = str(k)
            if k not in base:
                raise KeyError("overlay: %s に無いキー %s" % (".".join(path) or "(root)", k))
            out[k] = _merge(base[k], v, path + (k,))
        return out
    return over


def _read(path):
    with open(path, encoding="utf-8") as fp:
        doc = yaml.safe_load(fp) or {}
    if not isinstance(doc, dict):
        raise ValueError("%s: 最上位は mapping" % path)
    return doc


def resolve_option(name):
    """`kozax` のような名前を `options/kozax.yaml` に。パスならそのまま。"""
    if os.path.isfile(name):
        return name
    p = os.path.join(OPTIONS_DIR, name + ".yaml")
    if os.path.isfile(p):
        return p
    raise FileNotFoundError("option %r（%s）" % (name, p))


def load_policy(*names):
    """base と overlay を読んで `Policy` を返す。

    `load_policy()` は既定（`base_2024.yaml`）。`load_policy("kozax", "nocarry")` はレバーの overlay
    （`options/*.yaml`）を順に重ねる。先頭が既存の yaml のパスならそれを base にする。
    """
    base, overlays = BASE_YAML, names
    if names and os.path.isfile(names[0]) and names[0].endswith(".yaml") and not os.path.isfile(
            os.path.join(OPTIONS_DIR, os.path.basename(names[0]))):
        base, overlays = names[0], names[1:]
    sources: Dict[str, str] = {}
    data = fold(_read(base), (), sources)
    origin = [os.path.basename(base)]
    for ov in overlays:
        p = resolve_option(ov)
        ov_sources: Dict[str, str] = {}
        ov_data = fold(_read(p), (), ov_sources)
        data = _merge(data, ov_data, ())
        sources.update(ov_sources)
        origin.append(os.path.basename(p))
    return Policy(data=data, sources=sources, origin=tuple(origin))
