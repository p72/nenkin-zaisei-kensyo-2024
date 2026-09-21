/* ===========================================================================
 * hihokensha/cnum.py の差分テスト用ハーネス
 * ===========================================================================
 * 原本の `被保険者推計/stdfm.c` をそのままコンパイルしてリンクし、
 * `raund` と `read_csv` のふるまいを取り出す。
 *
 * 使い方
 *   harness raund <16進のdouble> <b>      → raund の結果を %a で出す
 *   harness csv   <ファイル>              → read_csv を EOF まで繰り返し、
 *                                            1行ごとに「戻り値 個数 値…」を出す
 *
 * 原本には手を入れない。`stdfm.c` を -c して一緒にリンクするだけ。
 * ======================================================================== */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "set.h"

/* stdfm.c の中で使う。原本では file_open.h が定義している */
double buffer_g[DATA_MAX];

int main(int ac, char **av)
{
	if (ac >= 2 && strcmp(av[1], "raund") == 0) {
		int i;
		for (i = 2; i + 1 < ac; i += 2) {
			double a = strtod(av[i], NULL);
			int b = atoi(av[i + 1]);
			printf("%a\n", raund(a, b));
		}
		return 0;
	}
	if (ac == 3 && strcmp(av[1], "csv") == 0) {
		FILE *fp = fopen(av[2], "r");
		int rc, dn, k;
		if (fp == NULL) { printf("open-failed\n"); return 1; }
		for (;;) {
			for (k = 0; k < DATA_MAX; ++k) buffer_g[k] = -12345.0;
			rc = read_csv(buffer_g, fp, &dn);
			printf("%d %d", rc, dn);
			for (k = 0; k <= dn && k < DATA_MAX; ++k)
				printf(" %a", buffer_g[k]);
			printf("\n");
			if (rc == EOF) break;
		}
		fclose(fp);
		return 0;
	}
	printf("usage\n");
	return 1;
}
