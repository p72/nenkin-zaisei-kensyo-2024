# -*- coding: utf-8 -*-
"""パッケージ内に生の原点（`- 2000` `- 2020` `SHONENDO` `UNDER_67` `C19(` 等）を
書かないこと。原点は `kosoku/axis.py` だけが持つ。

コメントと文字列（docstring）は除いて、コードのトークンだけを見る。
"""
import io
import os
import re
import tokenize

import pytest

from conftest import FAST

PKG = os.path.join(FAST, "kosoku")
ALLOWED = {"axis.py"}

# 生の原点の形。西暦・生年度の定数との加減算、移植版の原点の名前
PATTERNS = [
    re.compile(r"[-+]\s*(19[0-9]{2}|20[0-9]{2})\b"),
    re.compile(r"\b(SHONENDO|SUIKEISHONENDO|ECON_SHONENDO|UNDER_67|UNDER_64|N_O_NENDO)\b"),
    re.compile(r"\bC19\s*\("),
]


def _code_lines(path):
    """コメントと文字列を除いた各行のコード。"""
    src = open(path, encoding="utf-8").read()
    out = {}
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type in (tokenize.COMMENT, tokenize.STRING, tokenize.NL, tokenize.NEWLINE,
                        tokenize.INDENT, tokenize.DEDENT, tokenize.ENCODING):
            continue
        out.setdefault(tok.start[0], []).append(tok.string)
    return {ln: " ".join(parts) for ln, parts in out.items()}


def _files():
    for root, _, files in os.walk(PKG):
        for f in files:
            if f.endswith(".py") and f not in ALLOWED:
                yield os.path.join(root, f)


@pytest.mark.parametrize("path", sorted(_files()))
def test_生の原点が無い(path):
    bad = []
    for ln, code in _code_lines(path).items():
        for pat in PATTERNS:
            if pat.search(code):
                bad.append("%s:%d: %s" % (os.path.relpath(path, FAST), ln, code))
    assert not bad, "生の原点は axis.py だけに書く:\n" + "\n".join(bad)
