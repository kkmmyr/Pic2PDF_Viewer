import { renderHook, act } from '@testing-library/react';
import { vi, describe, it, expect } from 'vitest';
import { useDialogSubmit } from '@/hooks/library/useDialogSubmit';

describe('useDialogSubmit', () => {
    it('初期状態は saving=false / error=null', () => {
        const { result } = renderHook(() => useDialogSubmit(vi.fn()));
        expect(result.current.saving).toBe(false);
        expect(result.current.error).toBeNull();
    });

    it('handleSubmit 成功で onClose が呼ばれ、error は null のまま、saving は false に戻る', async () => {
        const onClose = vi.fn();
        const { result } = renderHook(() => useDialogSubmit(onClose));

        await act(async () => {
            await result.current.handleSubmit(async () => {});
        });

        expect(onClose).toHaveBeenCalledTimes(1);
        expect(result.current.error).toBeNull();
        expect(result.current.saving).toBe(false);
    });

    it('handleSubmit 失敗で error が設定され、onClose は呼ばれない', async () => {
        const onClose = vi.fn();
        const { result } = renderHook(() => useDialogSubmit(onClose));

        await act(async () => {
            await result.current.handleSubmit(async () => {
                throw new Error('保存エラー');
            });
        });

        expect(onClose).not.toHaveBeenCalled();
        expect(result.current.error).toBe('保存エラー');
        expect(result.current.saving).toBe(false);
    });

    it('Error 以外の throw では fallbackErrorMsg がエラーになる', async () => {
        const { result } = renderHook(() => useDialogSubmit(vi.fn()));

        await act(async () => {
            await result.current.handleSubmit(async () => {
                throw 'string error';
            });
        });

        expect(result.current.error).toBe('保存に失敗しました。'); // デフォルト fallback
    });

    it('fallbackErrorMsg を上書きできる', async () => {
        const { result } = renderHook(() => useDialogSubmit(vi.fn(), '更新失敗'));

        await act(async () => {
            await result.current.handleSubmit(async () => {
                throw 42;
            });
        });

        expect(result.current.error).toBe('更新失敗');
    });

    it('setError で外部からエラーをクリアできる', async () => {
        const { result } = renderHook(() => useDialogSubmit(vi.fn()));

        await act(async () => {
            await result.current.handleSubmit(async () => {
                throw new Error('e');
            });
        });
        expect(result.current.error).toBe('e');

        act(() => result.current.setError(null));
        expect(result.current.error).toBeNull();
    });

    it('handleSubmit 開始時に前回の error がクリアされる', async () => {
        const { result } = renderHook(() => useDialogSubmit(vi.fn()));

        await act(async () => {
            await result.current.handleSubmit(async () => {
                throw new Error('first');
            });
        });
        expect(result.current.error).toBe('first');

        await act(async () => {
            await result.current.handleSubmit(async () => {});
        });
        expect(result.current.error).toBeNull();
    });
});
