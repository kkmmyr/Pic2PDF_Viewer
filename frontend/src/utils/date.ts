/**
 * 日付フォーマットユーティリティ（Phase 54-6）。
 *
 * 旧来は `new Date(...).toLocaleDateString()` / `toLocaleString()` を直書きし、
 * `isNaN(d.getTime())` のフォールバックも各箇所で個別実装していた。
 * このモジュールに集約することで「無効値はそのまま返す / フォールバック値を返す」
 * 挙動を統一する。
 */

/**
 * Unix 秒（10 桁）を `YYYY/MM/DD` 形式（OS ロケール依存）でフォーマット。
 * `null` / `undefined` / 0 の場合は空文字を返す。
 */
export function formatTimestampJa(unixSec: number | null | undefined): string {
    if (!unixSec) return '';
    const d = new Date(unixSec * 1000);
    if (isNaN(d.getTime())) return '';
    return d.toLocaleDateString();
}

/**
 * ISO 文字列を `2026/05/06` のような ja-JP 短縮日付でフォーマット。
 * パース失敗時は元の ISO 文字列をそのまま返す（検査・デバッグ用途）。
 */
export function formatDateJa(iso: string | null | undefined): string {
    if (!iso) return '';
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    return d.toLocaleDateString('ja-JP', { year: 'numeric', month: '2-digit', day: '2-digit' });
}

/**
 * ISO 文字列を `2026/05/06 12:34:56` のような ja-JP 日時でフォーマット。
 * パース失敗時は元の ISO 文字列を、`null` の場合は em-dash `'—'` を返す。
 */
export function formatDateTimeJa(iso: string | null | undefined): string {
    if (!iso) return '—';
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    return d.toLocaleString('ja-JP');
}
