# -*- coding: utf-8 -*-
"""
厚生年金/給付費推計/main.cpp の忠実移植（②の入口）
====================================================
70 行。標準入力から4つ読んで、制度ごとに `sepsd()` を回す。

    key     試算モード（11 通常 / 12 過去分 / 13 受給者分）
    iname   試算番号（4桁）
    iecon   経済要素ファイル番号（4桁）
    iwname  外枠の試算番号（4桁）

    seidver = 1
    zero_init()
    cntl()                      ← 標準入力から設定を6つ読む

    for pseid in 0..5:
        if pseid in (2, 3): continue
        konen = 1 if pseid == 0 else 0
        if key in (11, 12, 13):
            zero_sepsd(); sepsd()

`pseid` は 0 厚生年金 / 1 国家公務員共済 / 4 地方公務員共済 /
5 私立学校共済。**2 と 3 は飛ばす**（旧・日本鉄道共済と
旧・農林漁業団体共済の枠が空いている）。

`if (true)` で囲んである
------------------------
```c
if (true) {
  cout << "試算モード(KEY番号)を設定して下さい" << "\\n" … ;
  cin >> key;
} else {
  key = 11;
}
```

`else` は到達しない。`key` を直書きに切り替えるつもりだった跡
（F9 の仲間）。移植版も `if True:` と書いて残す。

`key_condition` は常に真
------------------------
```c
bool key_condition;
key_condition = key == 11 || key == 12 || key == 13;
if(key_condition) { … }
```

`cntl()` が `key` を読み直さないので、`main` が読んだ値のまま。
11・12・13 以外を入れると**何も計算せずに終わる**（エラーにならない）。

`assert(iwname >= 1000)` だけ検査がある
---------------------------------------
外枠の試算番号は4桁でないと `fopn()` が開くパスが狂うので
`assert` がある。`key` `iname` `iecon` には無い。
`-DNDEBUG` で建てるとこれも消える。

走らせ方
--------
```bash
SUURI_PREFIX=work python3 検証/移植/emp_kyufu/main.py <<< $'11\\n3001\\n3001\\n3001\\n4\\n0\\n0\\n0\\n0\\n0'
```

前の4つが `main` のぶん、あとの6つが `cntl()` のぶん
（`seimei` `flg_part` `flg_sigo` `flg_kozax` `houjou` `flg_inout`）。
"""
import sys

import cntl as _cntl
import glva
import sepsd as _sepsd
from cinstream import Cin
from glva import G

__all__ = ["main"]


def main(cin=None):
    """main.cpp:10 int main(void) の忠実移植。"""
    if cin is None:
        cin = Cin.from_stdin()

    if True:                    # 原本は `if (true)`。else は到達しない
        print("試算モード(KEY番号)を設定して下さい")
        print("11: 通常試算")
        print("12: 過去分試算")
        print("13: 受給者分試算")
        G.key = cin.int_()
    else:
        G.key = 11

    print("")
    print("試算番号を設定して下さい(整数：４桁)")
    G.iname = cin.int_()
    print("経済要素ファイル番号を設定して下さい(整数：４桁)")
    G.iecon = cin.int_()
    print("外枠の試算番号を設定して下さい(整数：４桁)")
    G.iwname = cin.int_()
    assert G.iwname >= 1000

    G.seidver = 1

    glva.zero_init()

    _cntl.cntl(cin)

    print("各制度についての推計を実行します。")
    for pseid in range(0, 5 + 1):
        G.pseid = pseid             # 原本は GLOBAL_FOR（グローバルの pseid）

        if pseid == 2 or pseid == 3:
            continue

        if pseid == 0:
            G.konen = 1
        else:
            G.konen = 0

        # 原本は bool key_condition に入れてから見る。常に真
        key_condition = (G.key == 11 or G.key == 12 or G.key == 13)

        if key_condition:
            if pseid == 0:
                print("--- 厚生年金の推計を開始します ---")
            elif pseid == 1:
                print("--- 国家公務員共済組合の推計を開始します ---")
            elif pseid == 4:
                print("--- 地方公務員共済組合の推計を開始します ---")
            elif pseid == 5:
                print("--- 私立学校共済組合の推計を開始します ---")

            glva.zero_sepsd()
            _sepsd.sepsd()

    return 0


if __name__ == "__main__":
    sys.exit(main())
