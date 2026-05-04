import { useCallback, useState } from 'react';

interface AssignParams {
    title: string;
    index: number | number[];
    id?: string;
}

interface Options {
    currentPath: string;
    assignSeries: (path: string, names: string[], params: AssignParams) => Promise<unknown>;
    unassignSeries: (path: string, names: string[]) => Promise<unknown>;
    runAsync: <T>(
        fn: () => Promise<T>,
        errorMessage: string,
        opts?: { rethrow?: boolean },
    ) => Promise<T | undefined>;
}

/**
 * SeriesEditDialog の open/close 状態と、対象書籍へのシリーズ割り当て・解除ハンドラを集約。
 *
 * - `target`: 編集中の書籍名（null = ダイアログ閉じ）
 * - `open(name)` / `close()`: ダイアログ開閉
 * - `assign(params)` / `unassign()`: 対象書籍に対する操作（失敗時は `runAsync` 経由で toast 表示）
 */
export function useSeriesEditDialog({
    currentPath, assignSeries, unassignSeries, runAsync,
}: Options) {
    const [target, setTarget] = useState<string | null>(null);

    const open = useCallback((name: string) => setTarget(name), []);
    const close = useCallback(() => setTarget(null), []);

    const assign = useCallback(async (params: AssignParams) => {
        if (!target) return;
        await runAsync(
            () => assignSeries(currentPath, [target], params),
            'シリーズ割り当てに失敗しました。',
            { rethrow: true },
        );
    }, [target, assignSeries, currentPath, runAsync]);

    const unassign = useCallback(async () => {
        if (!target) return;
        await runAsync(
            () => unassignSeries(currentPath, [target]),
            'シリーズ解除に失敗しました。',
            { rethrow: true },
        );
    }, [target, unassignSeries, currentPath, runAsync]);

    return { target, open, close, assign, unassign };
}
