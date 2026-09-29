# -*- coding: utf-8 -*-
"""`base_2024.yaml` の種が移植版の引用先と一致すること
======================================================
葉ごとに

- `port: system.module.NAME[idx]` があれば、その属性の値と `value` が一致する
  （移植版は `portpath.select()` で読み取り専用に import する）
- なければ `match:`（省略時は `value` の文字列）が `source: file.py:LINE` の行に
  書かれている

を確かめる。`source:` が `esri:`（外部データ）や `kosoku/`・`検証/` で始まる
ものは移植版の外なので飛ばす。
"""
import importlib
import os
import re
import sys

import pytest
import yaml

from conftest import FAST, PORT

from kosoku.policy.load import BASE_YAML, load_policy     # noqa: E402

sys.path.insert(0, PORT)
from portpath import select                               # noqa: E402

LEAF_KEYS = {"value", "source", "match", "port", "note"}
SRC = re.compile(r"^([A-Za-z0-9_]+/[A-Za-z0-9_]+\.py):(\d+)$")


def _leaves(node, prefix=()):
    if isinstance(node, dict) and "value" in node and set(node) <= LEAF_KEYS:
        yield ".".join(prefix), node
        return
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _leaves(v, prefix + (str(k),))


def _all():
    doc = yaml.safe_load(open(BASE_YAML, encoding="utf-8"))
    return list(_leaves(doc))


LEAVES = _all()
_LINES = {}


def _line(rel, n):
    if rel not in _LINES:
        _LINES[rel] = open(os.path.join(PORT, rel), encoding="utf-8").read().split("\n")
    L = _LINES[rel]
    assert 1 <= n <= len(L), "%s:%d は範囲外（%d 行）" % (rel, n, len(L))
    return L[n - 1]


def _port_value(spec):
    """`system.module.NAME[idx]…` を引く。"""
    m = re.match(r"^([a-z_]+)\.([a-z_0-9]+)\.([A-Za-z_][A-Za-z0-9_]*)((?:\[[^\]]+\])*)$", spec)
    assert m, "port の形が違う: %s" % spec
    system, module, name, idx = m.groups()
    select("clib", system)
    mod = importlib.import_module(module)
    v = getattr(mod, name)
    for i in re.findall(r"\[([^\]]+)\]", idx):
        v = v[int(i)] if isinstance(v, (list, tuple)) else v[i]
    return v


def _render(value):
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def test_全項目に出典がある():
    missing = [p for p, leaf in LEAVES if not leaf.get("source")]
    assert not missing, "source: が無い:\n" + "\n".join(missing)
    pol = load_policy()
    assert not pol.unsourced(), pol.unsourced()


@pytest.mark.parametrize("path, leaf", LEAVES, ids=[p for p, _ in LEAVES])
def test_種が引用先と一致(path, leaf):
    src = leaf["source"]
    m = SRC.match(src)
    if not m:
        pytest.skip("移植版の外: %s" % src)
    rel, n = m.group(1), int(m.group(2))
    line = _line(rel, n)
    if "port" in leaf:
        got = _port_value(leaf["port"])
        want = leaf["value"]
        if isinstance(want, list):
            assert list(got) == list(want), "%s: port %s\n  got  %r\n  want %r" % (
                path, leaf["port"], list(got), want)
        elif isinstance(want, dict):
            assert {int(k): v for k, v in dict(got).items()} == {int(k): v for k, v in want.items()}, \
                "%s: port %s\n  got  %r\n  want %r" % (path, leaf["port"], dict(got), want)
        else:
            assert got == want, "%s: port %s = %r、yaml は %r" % (path, leaf["port"], got, want)
        # 行も引けていること（行番号が古くなっていないか）
        assert leaf["port"].rsplit(".", 1)[1].split("[")[0] in line, \
            "%s: %s:%d に %s が無い: %r" % (path, rel, n, leaf["port"], line)
    else:
        text = leaf.get("match")
        text = _render(leaf["value"]) if text is None else str(text)
        assert text in line, "%s: %s:%d に %r が無い: %r" % (path, rel, n, text, line.strip())
