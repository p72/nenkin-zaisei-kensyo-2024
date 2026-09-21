# -*- coding: utf-8 -*-
"""
被保険者推計/main.c の忠実移植
==============================
①の入口。12個の関数を順に呼ぶだけ（`main.c:9-55`）。

    zero        配列を 0 にする（C では最初から 0 なので何もしない）
    cntl        標準入力から7つの設定を読む
    readdata    入力CSVを17本読む
    setjinko    年央の人口から年度末の人口を作る
    simlroud    労働力・就業者・雇用者・自営業者と総労働時間
    simlkyos    共済3制度の2号
    simlkou     厚年の2号
    simlichisan 1号・3号・未加入外
    simlpart    適用拡大（パート）
    fout        本体の出力（61本）
    roudfout    労働力の出力（41本）
    cutout      調整率の出力（1本）

各段のあとに `printf("…終了\\n")` を出す。最後に `fclose(fp_err)`。

**順番が仕様**で、後ろの段が前の段の結果を使う。とくに `simlpart` は
`ichigou` / `sangou` を書き換えるので、`fout` より前に来る必要がある。

動かし方
--------
    SUURI_PREFIX=work python3 検証/移植/hihokensha/main.py < 入力.txt

入力は `検証/実行/run_pipeline.sh` が①に流すものと同じ7行。

    3001   試算番号
    0      適用拡大の区分（MODE）
    0      基礎45年化（MODE45）
    1      出生率（JIN）
    1      死亡率（QX）
    0      入国超過（NC）
    1      労働力率（ROUDR）
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_CLIB = os.path.join(os.path.dirname(_HERE), "clib")
if _CLIB not in sys.path:
    sys.path.append(_CLIB)

from cscan import Scan                                    # noqa: E402
import glva                                               # noqa: E402
import cntl as _cntl                                      # noqa: E402
import readdata as _readdata                              # noqa: E402
import setjinko as _setjinko                              # noqa: E402
import simlroud as _simlroud                              # noqa: E402
import simlkyos as _simlkyos                              # noqa: E402
import simlkou as _simlkou                                # noqa: E402
import simlichisan as _simlichisan                        # noqa: E402
import simlpart as _simlpart                              # noqa: E402
import fout as _fout                                      # noqa: E402
import roudfout as _roudfout                              # noqa: E402
import cutout as _cutout                                  # noqa: E402
from glva import G                                        # noqa: E402

__all__ = ["run", "main"]

# main.c:14-48。呼ぶ順と、終わったときに出す名前
_STAGES = (
    ("zero", lambda scan: glva.zero()),
    ("cntl", lambda scan: _cntl.cntl(scan)),
    ("readdata", lambda scan: _readdata.readdata()),
    ("setjinko", lambda scan: _setjinko.setjinko()),
    ("simlroud", lambda scan: _simlroud.simlroud()),
    ("simlkyos", lambda scan: _simlkyos.simlkyos()),
    ("simlkou", lambda scan: _simlkou.simlkou()),
    ("simlichisan", lambda scan: _simlichisan.simlichisan()),
    ("simlpart", lambda scan: _simlpart.simlpart()),
    ("fout", lambda scan: _fout.fout()),
    ("roudfout", lambda scan: _roudfout.roudfout()),
    ("cutout", lambda scan: _cutout.cutout()),
)


def run(scan):
    """main.c:9 の忠実移植。`scan` は `clib/cscan.py` の `Scan`。"""
    print("start")
    for name, fn in _STAGES:
        fn(scan)
        print(f"{name}終了")
    if G.fp_err is not None:
        G.fp_err.close()
        G.fp_err = None
    print("end")
    return 0


def main(argv=None):
    return run(Scan.from_stdin())


if __name__ == "__main__":
    raise SystemExit(main())
