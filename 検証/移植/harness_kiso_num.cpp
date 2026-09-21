/* 基礎年金の数値のふるまいを原本から取り出すハーネス
 * ====================================================
 * 原本の `基礎年金/stdfm.c` と `econ.c` を**無修正でコンパイルして
 * リンク**し、`Round` / `read_data` / `read_str` / `econ.c の round` の
 * 答えを倍精度のビット列（`%a`）で出す。移植版と突き合わせるため。
 *
 * `econ.c` はグローバル変数を `extern` で参照するので、`main.c` と
 * 同じやり方（ガードのマクロを先に立ててから include）で実体を作る
 * 翻訳単位を1つ足してリンクする。`econ()` は呼ばない。
 *
 *   ./h round  <a> <b> [<a> <b> ...]     Round( a , b ) を %a で
 *   ./h ground <a> <n> [<a> <n> ...]     econ.c の round( a , n ) を %a で
 *   ./h csv    <path>                    read_data を EOF まで
 *   ./h str    <path>                    read_str を EOF まで
 *
 * `csv` は1行ごとに「戻り値 data_number buffer[0..data_number]」を出す。
 * 呼び出し側の `double buffer[DATA_MAX]` を**使い回す**ので、読み切った
 * 個数より先に前の行の値が残るふるまいもそのまま見える（そこは
 * `-1` 個ぶん多く出して確かめる）。
 */
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <iostream>
#include "snaps.h"

using namespace std;

/* econ.c が自前に定義している round（`std::round` とは別物） */
double round(double a, int n);

int main(int argc, char *argv[])
{
	if (argc < 2) {
		fprintf(stderr, "usage: %s round|ground|csv|str ...\n", argv[0]);
		return 2;
	}

	if (strcmp(argv[1], "round") == 0) {
		for (int i = 2; i + 1 < argc; i += 2) {
			double a = atof(argv[i]);
			int b = atoi(argv[i + 1]);
			printf("%d\n", Round(a, b));
		}
		return 0;
	}

	if (strcmp(argv[1], "ground") == 0) {
		for (int i = 2; i + 1 < argc; i += 2) {
			double a = atof(argv[i]);
			int n = atoi(argv[i + 1]);
			printf("%a\n", round(a, n));
		}
		return 0;
	}

	if (strcmp(argv[1], "csv") == 0) {
		FILE *fp = fopen(argv[2], "r");
		if (fp == NULL) { fprintf(stderr, "open failed\n"); return 1; }
		/* 原本の呼び出し側と同じく初期化しない自動変数……にすると
		 * 突き合わせようがないので 0 で埋めてから使い回す */
		static double buffer[DATA_MAX];
		for (int i = 0; i < DATA_MAX; i++) buffer[i] = 0.0;
		int data_number;
		int value;
		int line = 0;
		do {
			value = read_data(buffer, fp, &data_number);
			printf("%d %d", value, data_number);
			/* 読み切った個数より2つ先まで出す（残り値の確認） */
			int upto = data_number + 2;
			if (upto > 20) upto = 20;
			for (int i = 0; i <= upto; i++) printf(" %a", buffer[i]);
			printf("\n");
			line++;
		} while (value != EOF && line < 10000);
		fclose(fp);
		return 0;
	}

	if (strcmp(argv[1], "str") == 0) {
		FILE *fp = fopen(argv[2], "r");
		if (fp == NULL) { fprintf(stderr, "open failed\n"); return 1; }
		static char buffer[DATA_MAX][BUFFER_MAX];
		for (int i = 0; i < DATA_MAX; i++) buffer[i][0] = '\0';
		int data_number;
		int value;
		int line = 0;
		do {
			value = read_str(buffer, fp, &data_number);
			printf("%d %d", value, data_number);
			int upto = data_number + 2;
			if (upto > 20) upto = 20;
			for (int i = 0; i <= upto; i++) printf(" [%s]", buffer[i]);
			printf("\n");
			line++;
		} while (value != EOF && line < 10000);
		fclose(fp);
		return 0;
	}

	fprintf(stderr, "unknown subcommand %s\n", argv[1]);
	return 2;
}
