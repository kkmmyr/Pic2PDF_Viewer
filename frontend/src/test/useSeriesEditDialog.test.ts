import { renderHook, act } from '@testing-library/react';
import { vi, describe, it, expect } from 'vitest';
import { useSeriesEditDialog } from '../hooks/library/useSeriesEditDialog';

const setup = () => {
    const assignSeries = vi.fn().mockResolvedValue('sid');
    const unassignSeries = vi.fn().mockResolvedValue(undefined);
    // runAsync は本物の挙動を模擬: fn を await して、エラーは握り潰す（呼び出し元で rethrow:true 指定可）
    const runAsync = vi.fn(
        async <T>(
            fn: () => Promise<T>,
            _errorMessage: string,
            _opts?: { rethrow?: boolean },
        ): Promise<T | undefined> => {
            try {
                return await fn();
            } catch {
                return undefined;
            }
        },
    );

    type RunAsync = Parameters<typeof useSeriesEditDialog>[0]['runAsync'];
    const hook = renderHook(() =>
        useSeriesEditDialog({
            currentPath: 'sub',
            assignSeries,
            unassignSeries,
            // vi.fn() の Mock 型は <T> 付きジェネリック関数型に直接代入できないため cast
            runAsync: runAsync as unknown as RunAsync,
        }),
    );

    return { ...hook, assignSeries, unassignSeries, runAsync };
};

describe('useSeriesEditDialog', () => {
    it('初期 target は null', () => {
        const { result } = setup();
        expect(result.current.target).toBeNull();
    });

    it('open(name) で target が設定される', () => {
        const { result } = setup();
        act(() => result.current.open('book.pdf'));
        expect(result.current.target).toBe('book.pdf');
    });

    it('close() で target=null', () => {
        const { result } = setup();
        act(() => result.current.open('x'));
        act(() => result.current.close());
        expect(result.current.target).toBeNull();
    });

    it('assign(): target ありで assignSeries(currentPath, [target], params) が呼ばれる', async () => {
        const { result, assignSeries } = setup();
        act(() => result.current.open('book.pdf'));

        await act(async () => {
            await result.current.assign({ title: 'X', index: 1 });
        });

        expect(assignSeries).toHaveBeenCalledWith('sub', ['book.pdf'], { title: 'X', index: 1 });
    });

    it('assign(): target=null では assignSeries が呼ばれない', async () => {
        const { result, assignSeries } = setup();
        await act(async () => {
            await result.current.assign({ title: 'X', index: 1 });
        });
        expect(assignSeries).not.toHaveBeenCalled();
    });

    it('unassign(): target ありで unassignSeries(currentPath, [target]) が呼ばれる', async () => {
        const { result, unassignSeries } = setup();
        act(() => result.current.open('y.pdf'));

        await act(async () => {
            await result.current.unassign();
        });

        expect(unassignSeries).toHaveBeenCalledWith('sub', ['y.pdf']);
    });

    it('unassign(): target=null では unassignSeries が呼ばれない', async () => {
        const { result, unassignSeries } = setup();
        await act(async () => {
            await result.current.unassign();
        });
        expect(unassignSeries).not.toHaveBeenCalled();
    });

    it('assign / unassign 共に runAsync 経由で実行される（rethrow:true 指定）', async () => {
        const { result, runAsync } = setup();
        act(() => result.current.open('book.pdf'));

        await act(async () => {
            await result.current.assign({ title: 'X', index: 1 });
        });

        const callOpts = runAsync.mock.calls[0][2];
        expect(callOpts).toEqual({ rethrow: true });

        await act(async () => {
            await result.current.unassign();
        });
        expect(runAsync.mock.calls[1][2]).toEqual({ rethrow: true });
    });
});
