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

describe('moveMultipleByIndex (AT semantic)', () => {
    it('単一要素の移動は arrayMove と等価', () => {
        // [A,B,C,D,E], 移動 [1] (=B), active=1, target=3
        //   → 結果 [A,C,D,B,E]（B が D のあった位置 = idx 3 に着地）
        // arrayMove(arr, 1, 3) = [A,C,D,B,E] と同じ
        const result = moveMultipleByIndex(['A', 'B', 'C', 'D', 'E'], [1], 1, 3);
        expect(result).toEqual(['A', 'C', 'D', 'B', 'E']);
    });

    it('単独移動でも arrayMove 結果と一致（target が末尾）', () => {
        // [A,B,C,D,E], 移動 [0] (=A), active=0, target=4
        //   → 結果 [B,C,D,E,A]
        const result = moveMultipleByIndex(['A', 'B', 'C', 'D', 'E'], [0], 0, 4);
        expect(result).toEqual(['B', 'C', 'D', 'E', 'A']);
    });

    it('グループ active=先頭: active が target にできる限り近づくよう配置', () => {
        // [A,B,C,D,E], 移動 [0,2] (=A,C), active=0 (=A), target=4
        //   → A を idx 4 に置きたいが C も入れるためクランプされ A=3, C=4
        //   → 結果 [B,D,E,A,C]
        const result = moveMultipleByIndex(['A', 'B', 'C', 'D', 'E'], [0, 2], 0, 4);
        expect(result).toEqual(['B', 'D', 'E', 'A', 'C']);
    });

    it('グループ active=末尾: active が target にぴったり着地、他はその前に', () => {
        // [A,B,C,D,E], 移動 [0,2] (=A,C), active=2 (=C), target=4
        //   → C を idx 4 に置く、A は C の直前で idx 3
        //   → 結果 [B,D,E,A,C]
        const result = moveMultipleByIndex(['A', 'B', 'C', 'D', 'E'], [0, 2], 2, 4);
        expect(result).toEqual(['B', 'D', 'E', 'A', 'C']);
    });

    it('movedIndices の元の相対順を保つ（active 同じなら順序逆でも同結果）', () => {
        const arr = ['A', 'B', 'C', 'D'];
        const r1 = moveMultipleByIndex(arr, [0, 2], 0, 3);
        const r2 = moveMultipleByIndex(arr, [2, 0], 0, 3);
        expect(r1).toEqual(r2);
    });

    it('targetIndex が movedIndices に含まれる場合は何もしない', () => {
        const result = moveMultipleByIndex(['A', 'B', 'C', 'D'], [0, 2], 0, 0);
        expect(result).toEqual(['A', 'B', 'C', 'D']);
    });

    it('targetIndex=0 で先頭への移動でも正しく動く', () => {
        // [A,B,C,D], 移動 [2,3] (=C,D), active=2 (=C), target=0
        //   → C を idx 0 に置く、D は idx 1
        //   → 結果 [C,D,A,B]
        const result = moveMultipleByIndex(['A', 'B', 'C', 'D'], [2, 3], 2, 0);
        expect(result).toEqual(['C', 'D', 'A', 'B']);
    });

    it('movedIndices が空なら元配列のコピーを返す', () => {
        const arr = ['A', 'B', 'C'];
        const result = moveMultipleByIndex(arr, [], 0, 1);
        expect(result).toEqual(arr);
        expect(result).not.toBe(arr);
    });

    it('連続した複数要素の移動でも active=先頭で正しく着地', () => {
        // [A,B,C,D,E], 移動 [1,2] (=B,C), active=1 (=B), target=4
        //   → B を idx 4 に置きたいが C も入れるためクランプ → B=3, C=4
        //   → 結果 [A,D,E,B,C]
        const result = moveMultipleByIndex(['A', 'B', 'C', 'D', 'E'], [1, 2], 1, 4);
        expect(result).toEqual(['A', 'D', 'E', 'B', 'C']);
    });
});
