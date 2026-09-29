# -*- coding: utf-8 -*-
"""①被保険者推計（移植版 `検証/移植/hihokensha/`）の高速版。

    inputs    17 本の CSV と設定（港 readdata / cntl）
    jinko     人口の整形と年央→年度末（港 setjinko）
    roudou    労働力・就業者・雇用者・総労働時間（港 simlroud）
    kounen    共済と厚年の2号（港 simlkyos / simlkou）
    ichisan   1号・3号・未加入外（港 simlichisan）
    part      適用拡大（パート）（港 simlpart）
    cutritu   マクロ経済スライドの調整率（港 cutout）
    output    58 分類の表と港の配置の CSV（港 fout / cutout）
    run       通し → `Waku`
"""
