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

/**
 * SQLite の `datetime('now')` が返す UTC 文字列を Date に変換する。
 *
 * SQLite の出力は `"2026-05-11 13:30:45"`（スペース区切り、タイムゾーン情報なし）。
 * JS の `new Date()` はこの形式をローカル時刻として誤解釈するため、明示的に
 * `"2026-05-11T13:30:45Z"` に整形してから Date 化する。
 * パース失敗時は `null` を返す。
 */
export function parseSqliteUtc(s: string | null | undefined): Date | null {
    if (!s) return null;
    // ISO 8601 風（`T` 区切り）にし、Z が無ければ付与
    const normalized = s.includes('T') ? s : s.replace(' ', 'T');
    const withZ = /[Zz]|[+-]\d{2}:?\d{2}$/.test(normalized) ? normalized : `${normalized}Z`;
    const d = new Date(withZ);
    return isNaN(d.getTime()) ? null : d;
}

/**
 * SQLite UTC 文字列を `2026/05/11 22:30` 形式の JST 表示に変換する。
 * 秒は表示しない（履歴一覧の簡略表示用）。
 * パース失敗時は元の文字列を、`null` の場合は em-dash `'—'` を返す。
 */
export function formatSqliteUtcAsJst(s: string | null | undefined): string {
    if (!s) return '—';
    const d = parseSqliteUtc(s);
    if (!d) return s;
    return d.toLocaleString('ja-JP', {
        timeZone: 'Asia/Tokyo',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
    });
}

/**
 * SQLite UTC タイムスタンプ 2 つから経過秒数を計算し、人間可読な文字列にする。
 *
 * 例: 170 秒 → `"2 分 50 秒"`、35 秒 → `"35 秒"`、3700 秒 → `"1 時間 1 分"`。
 * `finished` が `null` の場合は `null` を返す（呼び出し側で「進行中」等を表示）。
 * パース失敗 / 負値の場合も `null`。
 */
export function formatElapsedSeconds(
    asked: string | null | undefined,
    finished: string | null | undefined,
): string | null {
    const a = parseSqliteUtc(asked);
    const f = parseSqliteUtc(finished);
    if (!a || !f) return null;
    const sec = Math.round((f.getTime() - a.getTime()) / 1000);
    if (sec < 0) return null;
    if (sec < 60) return `${sec} 秒`;
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    if (m < 60) return s > 0 ? `${m} 分 ${s} 秒` : `${m} 分`;
    const h = Math.floor(m / 60);
    const mm = m % 60;
    return mm > 0 ? `${h} 時間 ${mm} 分` : `${h} 時間`;
}
