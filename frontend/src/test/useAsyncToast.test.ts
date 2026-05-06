import { renderHook } from '@testing-library/react';
import { vi, describe, it, expect } from 'vitest';
import { useAsyncToast } from '../hooks/useAsyncToast';

describe('useAsyncToast', () => {
    it('成功時は fn の戻り値を返し、showToast を呼ばない', async () => {
        const showToast = vi.fn();
        const { result } = renderHook(() => useAsyncToast(showToast));

        const ret = await result.current(async () => 'ok', '失敗');
        expect(ret).toBe('ok');
        expect(showToast).not.toHaveBeenCalled();
    });

    it('Error throw で errorMessage 経由のメッセージを error toast', async () => {
        const showToast = vi.fn();
        const { result } = renderHook(() => useAsyncToast(showToast));

        const ret = await result.current(async () => {
            throw new Error('boom');
        }, 'fallback msg');

        expect(ret).toBeUndefined();
        expect(showToast).toHaveBeenCalledWith('boom', 'error');
    });

    it('Error 以外の throw では fallback 文字列をそのまま toast', async () => {
        const showToast = vi.fn();
        const { result } = renderHook(() => useAsyncToast(showToast));

        await result.current(async () => {
            throw 'plain';
        }, 'fallback msg');

        expect(showToast).toHaveBeenCalledWith('fallback msg', 'error');
    });

    it('fallback が関数なら関数の戻り値を toast', async () => {
        const showToast = vi.fn();
        const { result } = renderHook(() => useAsyncToast(showToast));

        const fallback = (e: unknown) => `失敗: ${(e as Error).message}`;
        await result.current(async () => {
            throw new Error('内訳');
        }, fallback);

        expect(showToast).toHaveBeenCalledWith('失敗: 内訳', 'error');
    });

    it('options.rethrow=true で例外を再スローする', async () => {
        const showToast = vi.fn();
        const { result } = renderHook(() => useAsyncToast(showToast));

        let thrown: unknown;
        try {
            await result.current(
                async () => {
                    throw new Error('rethrown');
                },
                'fallback',
                { rethrow: true },
            );
        } catch (e) {
            thrown = e;
        }
        expect(thrown).toBeInstanceOf(Error);
        expect(showToast).toHaveBeenCalled();
    });

    it('成功時に rethrow=true でも何もスローしない', async () => {
        const showToast = vi.fn();
        const { result } = renderHook(() => useAsyncToast(showToast));

        const ret = await result.current(async () => 42, 'fallback', { rethrow: true });
        expect(ret).toBe(42);
        expect(showToast).not.toHaveBeenCalled();
    });
});
