/* ===========================================================================
 * clib/cppnum.py の差分テスト用ハーネス
 * ===========================================================================
 * `std::stoi` と `std::stod` のふるまいを、その場の libstdc++ から取り出す。
 * 値を埋め込まずに毎回コンパイルして問い合わせるので、標準ライブラリが
 * 変わったら気付ける。
 *
 * 引数に与えた文字列を1つずつ両方にかけて出す。
 *
 *   i <10進>  | i invalid | i range     std::stoi の結果
 *   d <%a>    | d invalid | d range     std::stod の結果
 *
 * 文字列は引数で渡すので、空白を含むものは呼び出し側が1引数として渡す。
 * ======================================================================== */
#include <cstdio>
#include <stdexcept>
#include <string>

int main(int ac, char **av){
	for (int i = 1; i < ac; ++i) {
		std::string s(av[i]);

		printf("i ");
		try { printf("%d\n", std::stoi(s)); }
		catch (const std::invalid_argument&) { printf("invalid\n"); }
		catch (const std::out_of_range&)     { printf("range\n"); }

		printf("d ");
		try { printf("%a\n", std::stod(s)); }
		catch (const std::invalid_argument&) { printf("invalid\n"); }
		catch (const std::out_of_range&)     { printf("range\n"); }
	}
	return 0;
}
