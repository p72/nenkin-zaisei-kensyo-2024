# -*- coding: utf-8 -*-
"""②厚生年金給付費推計の高速版（`検証/移植/emp_kyufu` の再実装）。

入口は `run.run(pol, case, emp_dir, waku_dir, econ_csv, qx_csv)`（4 制度）と
`output.to_port_csv(runs, case, outdir)`（港の配置で `shus.*` `kiso.*` `kaitea/b` を書く）。
"""
