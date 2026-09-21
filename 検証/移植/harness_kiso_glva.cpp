/* 基礎年金のグローバル変数の実体を作るだけの翻訳単位
 * ====================================================
 * 原本の `main.c` は、ガードのマクロを**先に立ててから**ヘッダを
 * include することでグローバル変数の実体を作る。
 *
 *   #ifdef MCNTL_H_INCLUDED
 *       #define EXTERN          ← 中身が空。つまり定義になる
 *   #else
 *       #define EXTERN extern
 *   #endif
 *
 * `harness_kiso_num.cpp` は `econ.c` をリンクするので、`econ.c` が
 * `extern` で参照しているグローバルの実体がどこかに必要になる。
 * `main.c` をそのまま持ってくると `main()` が衝突するので、
 * 同じ前置きだけを写したこのファイルを足す。
 */
#define MCNTL_H_INCLUDED
#define MECON_H_INCLUDED
#define MFILE_OPEN_H_INCLUDED
#define MKISO_H_INCLUDED
#define MKISOSU_H_INCLUDED
#define OPTION_H_INCLUDED
#define SNAPS_H_INCLUDED
#include <cstdio>
#include <cstring>
#include <iostream>
#include <cstdlib>
#include "snaps.h"
#include "mcntl.h"
#include "mecon.h"
#include "mkisosu.h"
#include "mfile_open.h"
#include "mkiso.h"
#include "option.h"
