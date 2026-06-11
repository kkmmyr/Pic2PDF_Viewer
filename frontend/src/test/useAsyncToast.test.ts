import { renderHook } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { toast } from 'sonner';
import { useAsyncToast } from '@/hooks/useAsyncToast';

vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

describe('useAsyncToast', () => {
    beforeEach(() => {
        vi.mocked(toast.error).mockClear();
    });

    it('成功時は fn の戻り値を返し、toast.error を呼ばない', async () => {
        const { result } = renderHook(() => useAsyncToast());

        const ret = await result.current(async () => 'ok', '失敗');
        expect(ret).toBe('ok');
        expect(toast.error).not.toHaveBeenCalled();
    });

    it('Error throw で errorMessage 経由のメッセージを error toast', async () => {
        const { result } = renderHook(() => useAsyncToast());

        const ret = await result.current(async () => {
            throw new Error('boom');
        }, 'fallback msg');

        expect(ret).toBeUndefined();
        expect(toast.error).toHaveBeenCalledWith('boom');
    });

    it('Error 以外の throw では fallback 文字列をそのまま toast', async () => {
        const { result } = renderHook(() => useAsyncToast());

        await result.current(async () => {
            throw 'plain';
        }, 'fallback msg');

        expect(toast.error).toHaveBeenCalledWith('fallback msg');
    });

    it('fallback が関数なら関数の戻り値を toast', async () => {
        const { result } = renderHook(() => useAsyncToast());

        const fallback = (e: unknown) => `失敗: ${(e as Error).message}`;
        await result.current(async () => {
            throw new Error('内訳');
        }, fallback);

        expect(toast.error).toHaveBeenCalledWith('失敗: 内訳');
    });

    it('options.rethrow=true で例外を再スローする', async () => {
        const { result } = renderHook(() => useAsyncToast());

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
        expect(toast.error).toHaveBeenCalled();
    });

    it('成功時に rethrow=true でも何もスローしない', async () => {
        const { result } = renderHook(() => useAsyncToast());

        const ret = await result.current(async () => 42, 'fallback', { rethrow: true });
        expect(ret).toBe(42);
        expect(toast.error).not.toHaveBeenCalled();
    });
});
