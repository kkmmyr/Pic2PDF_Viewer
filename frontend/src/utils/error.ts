/**
 * unknown 値からエラーメッセージを抽出する。
 *
 * `e instanceof Error ? e.message : fallback` の三項演算が散在していたため
 * 1 関数に集約する（Phase 54-5）。
 */
export function errorMessage(e: unknown, fallback: string): string {
    return e instanceof Error ? e.message : fallback;
}
