import { describe, it, expect } from 'vitest';
import { cmpJa } from '../utils/sort';

describe('cmpJa', () => {
    it('a < b で負の値を返す', () => {
        expect(cmpJa('a', 'b')).toBeLessThan(0);
    });

    it('a > b で正の値を返す', () => {
        expect(cmpJa('b', 'a')).toBeGreaterThan(0);
    });

    it('同一文字列で 0 を返す', () => {
        expect(cmpJa('same', 'same')).toBe(0);
    });

    it('日本語の五十音順', () => {
        expect(cmpJa('あ', 'い')).toBeLessThan(0);
        expect(cmpJa('い', 'あ')).toBeGreaterThan(0);
    });

    it('Array.sort のコンパレータとして動作する（英字）', () => {
        expect(['Charlie', 'Alpha', 'Bravo'].sort(cmpJa)).toEqual(['Alpha', 'Bravo', 'Charlie']);
    });

    it('日本語混在のソートで「あさひ」<「さくら」', () => {
        const sorted = ['さくら', 'あさひ'].sort(cmpJa);
        expect(sorted[0]).toBe('あさひ');
        expect(sorted[1]).toBe('さくら');
    });
});
