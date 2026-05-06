/**
 * 作者集合をグループ化キー（文字列）に変換する。
 *
 * - 元配列を破壊せず（スプレッドでコピー）
 * - 順序非依存にするため `sort()` を適用
 * - 区切り文字は `'\n'`（作者名に通常含まれない）
 *
 * 旧来は `[...authors].sort().join('\n')` が 9 箇所に散在していた（Phase 54-4）。
 */
export function authorsKey(authors: readonly string[] | undefined | null): string {
    return [...(authors ?? [])].sort().join('\n');
}
