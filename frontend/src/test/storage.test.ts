import { describe, it, expect, beforeEach, vi } from 'vitest';
import { getStorageJson, setStorageJson, removeStorage } from '../utils/storage';

describe('storage utils', () => {
    beforeEach(() => {
        localStorage.clear();
    });

    describe('getStorageJson', () => {
        it('未保存のキーは fallback を返す', () => {
            expect(getStorageJson('missing', { default: true })).toEqual({ default: true });
        });

        it('保存済みの JSON を復元する', () => {
            localStorage.setItem('k', JSON.stringify({ a: 1 }));
            expect(getStorageJson<{ a: number }>('k', { a: 0 })).toEqual({ a: 1 });
        });

        it('JSON 不正の場合は fallback を返す（throw しない）', () => {
            localStorage.setItem('broken', '{invalid');
            expect(getStorageJson('broken', 'fallback')).toBe('fallback');
        });

        it('localStorage.getItem が throw しても fallback を返す', () => {
            const spy = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
                throw new Error('blocked');
            });
            expect(getStorageJson('k', 'fallback')).toBe('fallback');
            spy.mockRestore();
        });

        it('空文字列は fallback を返す（raw が falsy のため）', () => {
            localStorage.setItem('empty', '');
            expect(getStorageJson('empty', 'fallback')).toBe('fallback');
        });

        it('JSON.stringify(null) は null として復元される', () => {
            localStorage.setItem('null-val', JSON.stringify(null));
            expect(getStorageJson('null-val', 'fallback')).toBeNull();
        });
    });

    describe('setStorageJson', () => {
        it('JSON 文字列として書き込む', () => {
            setStorageJson('k', { a: 1, b: 2 });
            expect(JSON.parse(localStorage.getItem('k')!)).toEqual({ a: 1, b: 2 });
        });

        it('プリミティブ値も書き込める', () => {
            setStorageJson('s', 'hello');
            expect(localStorage.getItem('s')).toBe(JSON.stringify('hello'));
        });

        it('localStorage.setItem が throw しても呼び出し側は throw しない', () => {
            const spy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
                throw new Error('quota exceeded');
            });
            expect(() => setStorageJson('k', { big: 'data' })).not.toThrow();
            spy.mockRestore();
        });

        it('保存後に getStorageJson で同じ値を取得できる', () => {
            setStorageJson('round', [1, 2, 3]);
            expect(getStorageJson<number[]>('round', [])).toEqual([1, 2, 3]);
        });
    });

    describe('removeStorage', () => {
        it('保存済みキーを削除する', () => {
            localStorage.setItem('k', 'v');
            removeStorage('k');
            expect(localStorage.getItem('k')).toBeNull();
        });

        it('存在しないキーで何も起きない', () => {
            expect(() => removeStorage('missing')).not.toThrow();
        });

        it('localStorage.removeItem が throw しても throw しない', () => {
            const spy = vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => {
                throw new Error('blocked');
            });
            expect(() => removeStorage('k')).not.toThrow();
            spy.mockRestore();
        });
    });
});
