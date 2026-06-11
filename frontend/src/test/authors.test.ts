import { describe, it, expect } from 'vitest';
import { authorsKey } from '@/utils/authors';

describe('authorsKey', () => {
    it('単一作者でその文字列を返す', () => {
        expect(authorsKey(['A'])).toBe('A');
    });

    it('複数作者は sort して \\n で結合する', () => {
        expect(authorsKey(['B', 'A'])).toBe('A\nB');
    });

    it('順序非依存（同じ集合なら同じキー）', () => {
        expect(authorsKey(['B', 'A', 'C'])).toBe(authorsKey(['C', 'A', 'B']));
    });

    it('空配列は空文字を返す', () => {
        expect(authorsKey([])).toBe('');
    });

    it('null は空文字を返す', () => {
        expect(authorsKey(null)).toBe('');
    });

    it('undefined は空文字を返す', () => {
        expect(authorsKey(undefined)).toBe('');
    });

    it('元配列を破壊しない（sort はコピーに対して行う）', () => {
        const original = ['B', 'A'];
        authorsKey(original);
        expect(original).toEqual(['B', 'A']);
    });

    it('重複を排除しない（実装どおり）', () => {
        expect(authorsKey(['A', 'A'])).toBe('A\nA');
    });

    it('日本語の作者名でも sort が安定する', () => {
        const k1 = authorsKey(['さくら', 'あさひ']);
        const k2 = authorsKey(['あさひ', 'さくら']);
        expect(k1).toBe(k2);
    });
});
