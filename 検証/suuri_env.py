# -*- coding: utf-8 -*-
"""
実行領域 /suuri/rev2024 の置き場所を決める
==========================================
原本は出力先も入力ファイルリストも `/suuri/rev2024` という絶対パスで持って
いる（専用UNIXサーバの固定構成が前提だった名残。仕様書 §12.1）。
ルート直下に書き込めない環境でも動くように、プレフィックスを付け替える。

    SUURI_PREFIX 未設定  →  <リポジトリ>/work/suuri/rev2024   （既定・root不要）
    SUURI_PREFIX=/       →  /suuri/rev2024                    （従来どおり）
    SUURI_PREFIX=/mnt/d  →  /mnt/d/suuri/rev2024

シェル側は 検証/実行/suuri_env.sh が同じ規則を実装しています。
"""
import os


def repo_root():
    """このファイルは <リポジトリ>/検証/ にあるので、親がルート。"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def suuri(*parts):
    """実行領域の下のパスを組む。suuri() で実行領域そのもの。"""
    prefix = os.environ.get('SUURI_PREFIX')
    if prefix is None:
        prefix = os.path.join(repo_root(), 'work')
    prefix = prefix.rstrip('/')
    return os.path.join(prefix + '/suuri/rev2024', *parts)


def describe():
    """どこを見ているかを1行で返す（スクリプトの冒頭表示用）。"""
    where = suuri()
    if not os.path.isdir(where):
        return f"{where}  （まだありません。検証/実行/run_pipeline.sh を先に実行）"
    return where
