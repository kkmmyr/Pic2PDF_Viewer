import { describe, it, expect } from 'vitest';
import { cmpJa, moveMultipleByIndex } from '../utils/sort';

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

describe('moveMultipleByIndex', () => {
    it('単一要素の移動は arrayMove と等価', () => {
        // [A,B,C,D,E], 移動 [0] を index 4 へ → 結果 [B,C,D,A,E]
        // 動作: A が remaining=[B,C,D,E] の adjustedTarget = 4-1 = 3 に挿入される
        const result = moveMultipleByIndex(['A', 'B', 'C', 'D', 'E'], [0], 4);
        expect(result).toEqual(['B', 'C', 'D', 'A', 'E']);
    });

    it('非連続な複数要素を targetIndex の直前にまとめて挿入する', () => {
        // [A,B,C,D,E], 移動 [0, 2] を index 4 へ → 結果 [B,D,A,C,E]
        const result = moveMultipleByIndex(['A', 'B', 'C', 'D', 'E'], [0, 2], 4);
        expect(result).toEqual(['B', 'D', 'A', 'C', 'E']);
    });

    it('movedIndices の元の相対順を保つ', () => {
        // 移動 [2, 0] と [0, 2] は同じ結果（昇順ソート後にスライス）
        const arr = ['A', 'B', 'C', 'D'];
        const r1 = moveMultipleByIndex(arr, [0, 2], 3);
        const r2 = moveMultipleByIndex(arr, [2, 0], 3);
        expect(r1).toEqual(r2);
    });

    it('targetIndex が movedIndices に含まれる場合は何もしない', () => {
        const result = moveMultipleByIndex(['A', 'B', 'C', 'D'], [0, 2], 0);
        expect(result).toEqual(['A', 'B', 'C', 'D']);
    });

    it('targetIndex が先頭（0）でも正しく動く', () => {
        const result = moveMultipleByIndex(['A', 'B', 'C', 'D'], [2, 3], 0);
        expect(result).toEqual(['C', 'D', 'A', 'B']);
    });

    it('movedIndices が空なら元配列のコピーを返す', () => {
        const arr = ['A', 'B', 'C'];
        const result = moveMultipleByIndex(arr, [], 1);
        expect(result).toEqual(arr);
        expect(result).not.toBe(arr); // shallow copy
    });

    it('連続した複数要素の移動でも元の相対順が維持される', () => {
        // [A,B,C,D,E], 移動 [1, 2] を index 4 へ → 結果 [A,D,B,C,E]
        const result = moveMultipleByIndex(['A', 'B', 'C', 'D', 'E'], [1, 2], 4);
        expect(result).toEqual(['A', 'D', 'B', 'C', 'E']);
    });
});
