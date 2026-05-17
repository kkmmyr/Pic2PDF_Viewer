import { describe, it, expect } from 'vitest';
import {
    formatDateJa,
    formatDateTimeJa,
    formatElapsedSeconds,
    formatSqliteUtcAsJst,
    formatTimestampJa,
    parseSqliteUtc,
} from '../utils/date';

describe('formatTimestampJa', () => {
    it('null で空文字', () => {
        expect(formatTimestampJa(null)).toBe('');
    });

    it('undefined で空文字', () => {
        expect(formatTimestampJa(undefined)).toBe('');
    });

    it('0 で空文字（falsy 扱い）', () => {
        expect(formatTimestampJa(0)).toBe('');
    });

    it('Unix 秒（10 桁）から非空の日付文字列を返す', () => {
        const out = formatTimestampJa(1700000000);
        expect(out).not.toBe('');
        expect(out.length).toBeGreaterThan(0);
    });

    it('NaN で空文字', () => {
        expect(formatTimestampJa(Number.NaN)).toBe('');
    });

    it('指定値で年（2023 または 2024）が含まれる程度の整合性', () => {
        // 1700000000 = 2023-11-14T22:13:20Z（タイムゾーン依存で前後する可能性）
        const out = formatTimestampJa(1700000000);
        expect(out).toMatch(/2023|2024/);
    });
});

describe('formatDateJa', () => {
    it('null で空文字', () => {
        expect(formatDateJa(null)).toBe('');
    });

    it('undefined で空文字', () => {
        expect(formatDateJa(undefined)).toBe('');
    });

    it('空文字は空文字を返す（falsy 扱い）', () => {
        expect(formatDateJa('')).toBe('');
    });

    it('ISO 文字列を ja-JP 短縮日付でフォーマット', () => {
        const out = formatDateJa('2026-05-06');
        expect(out).toContain('2026');
        expect(out).toContain('05');
        expect(out).toContain('06');
    });

    it('パース失敗時は元の ISO 文字列をそのまま返す', () => {
        expect(formatDateJa('not-a-date')).toBe('not-a-date');
    });
});

describe('formatDateTimeJa', () => {
    it('null は em-dash を返す', () => {
        expect(formatDateTimeJa(null)).toBe('—');
    });

    it('undefined は em-dash を返す', () => {
        expect(formatDateTimeJa(undefined)).toBe('—');
    });

    it('空文字は em-dash を返す（falsy 扱い）', () => {
        expect(formatDateTimeJa('')).toBe('—');
    });

    it('ISO 文字列を日時にフォーマットして年が含まれる', () => {
        const out = formatDateTimeJa('2026-05-06T12:34:56');
        expect(out).toContain('2026');
    });

    it('パース失敗時は元の ISO 文字列を返す', () => {
        expect(formatDateTimeJa('garbage')).toBe('garbage');
    });
});

describe('parseSqliteUtc', () => {
    it('null は null を返す', () => {
        expect(parseSqliteUtc(null)).toBe(null);
    });

    it('SQLite 形式（スペース区切り、Z なし）を JST として解釈', () => {
        const d = parseSqliteUtc('2026-05-11 13:30:45');
        expect(d).not.toBe(null);
        // JST 13:30:45 = UTC 04:30:45
        expect(d?.getUTCFullYear()).toBe(2026);
        expect(d?.getUTCMonth()).toBe(4); // 0-indexed
        expect(d?.getUTCDate()).toBe(11);
        expect(d?.getUTCHours()).toBe(4);
        expect(d?.getUTCMinutes()).toBe(30);
    });

    it('Z 付き ISO 8601 はそのまま UTC として解釈', () => {
        const d = parseSqliteUtc('2026-05-11T13:30:45Z');
        expect(d?.getUTCHours()).toBe(13);
    });

    it('+09:00 オフセット付き ISO 8601 はそのまま尊重', () => {
        const d = parseSqliteUtc('2026-05-11T22:30:45+09:00');
        expect(d?.getUTCHours()).toBe(13); // JST 22:30 = UTC 13:30
    });

    it('不正な文字列は null', () => {
        expect(parseSqliteUtc('not-a-date')).toBe(null);
    });
});

describe('formatSqliteUtcAsJst', () => {
    it('null は em-dash', () => {
        expect(formatSqliteUtcAsJst(null)).toBe('—');
    });

    it('JST 13:30 がそのまま 13:30 として表示される', () => {
        const out = formatSqliteUtcAsJst('2026-05-11 13:30:45');
        expect(out).toContain('2026');
        expect(out).toContain('13:30');
    });

    it('JST 23:30（深夜）は同日 23:30 として表示される', () => {
        const out = formatSqliteUtcAsJst('2026-05-11 23:30:00');
        expect(out).toContain('23:30');
        expect(out).toContain('11');
    });

    it('パース失敗時は元の文字列を返す', () => {
        expect(formatSqliteUtcAsJst('garbage')).toBe('garbage');
    });
});

describe('formatElapsedSeconds', () => {
    it('finished が null のとき null', () => {
        expect(formatElapsedSeconds('2026-05-11 13:30:00', null)).toBe(null);
    });

    it('asked が null のとき null', () => {
        expect(formatElapsedSeconds(null, '2026-05-11 13:30:00')).toBe(null);
    });

    it('60 秒未満は秒のみ', () => {
        expect(formatElapsedSeconds('2026-05-11 13:30:00', '2026-05-11 13:30:35')).toBe('35 秒');
    });

    it('60 秒以上 1 時間未満は 分 + 秒', () => {
        expect(formatElapsedSeconds('2026-05-11 13:30:00', '2026-05-11 13:32:50')).toBe(
            '2 分 50 秒',
        );
    });

    it('丁度 N 分なら秒部分は省略', () => {
        expect(formatElapsedSeconds('2026-05-11 13:30:00', '2026-05-11 13:32:00')).toBe('2 分');
    });

    it('1 時間以上は 時間 + 分', () => {
        expect(formatElapsedSeconds('2026-05-11 13:30:00', '2026-05-11 14:31:00')).toBe(
            '1 時間 1 分',
        );
    });

    it('丁度 N 時間なら分部分は省略', () => {
        expect(formatElapsedSeconds('2026-05-11 13:30:00', '2026-05-11 14:30:00')).toBe('1 時間');
    });

    it('finished が asked より前（負値）は null', () => {
        expect(formatElapsedSeconds('2026-05-11 13:32:00', '2026-05-11 13:30:00')).toBe(null);
    });
});
