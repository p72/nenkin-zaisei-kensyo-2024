# -*- coding: utf-8 -*-
"""制度のデータ化。`model.py` が型、`load.py` が yaml の読み手、
`base_2024.yaml` が現行制度の種（値ごとに `source:` で移植版の行を引く）。"""
from .load import load_policy, BASE_YAML   # noqa: F401
from .model import Policy                  # noqa: F401
