import { describe, it, expect } from 'vitest';
import { formatTimestampJa, formatDateJa, formatDateTimeJa } from '../utils/date';

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
