import { useCallback } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import type { BookMetaEntry, BookMetaMap } from '@/types';
import { API_ENDPOINTS } from '@/config/api';
import apiClient from '@/config/api_client';
import { metaQueryKey, makeBookMetaKey } from './useBookMetaCore';

interface AssignSeriesVars {
    path: string;
    names: string[];
    params: { title: string; index: number | number[]; id?: string };
}

interface UnassignSeriesVars {
    path: string;
    names: string[];
}

interface ReorderSeriesVars {
    path: string;
    names: string[];
    seriesId: string;
}

/**
 * シリーズ手動編集系フック（割り当て / 解除 / DnD 並べ替え）。
 *
 * - assignSeries  : 悲観的更新（サーバー発行の series_id が必要）
 * - unassignSeries: 楽観的更新 + エラー時ロールバック
 * - reorderSeries : 楽観的更新 + エラー時ロールバック
 */
export function useBookSeries(source: string) {
    const queryClient = useQueryClient();

    // ── assignSeries ────────────────────────────────────────────────────────
    const { mutateAsync: mutateAssign } = useMutation({
        mutationFn: ({ path, names, params }: AssignSeriesVars) =>
            apiClient.post<unknown, { id: string; updated_count: number }>(
                API_ENDPOINTS.SERIES_ASSIGN,
                { path, names, ...params, source },
            ),
        onSuccess: (res, { path, names, params }) => {
            const sid = res.id;
            const indexFor = (i: number): number =>
                Array.isArray(params.index) ? params.index[i] : params.index;

            queryClient.setQueryData<BookMetaMap>(metaQueryKey(source), (prev = {}) => {
                const next = { ...prev };
                names.forEach((name, i) => {
                    const key = makeBookMetaKey(path, name);
                    const existing = next[key] ?? { authors: [] };
                    next[key] = {
                        ...existing,
                        series_id: sid,
                        series_title: params.title,
                        series_index: indexFor(i),
                    };
                });
                return next;
            });
        },
    });

    // ── unassignSeries ──────────────────────────────────────────────────────
    const { mutateAsync: mutateUnassign } = useMutation({
        mutationFn: ({ path, names }: UnassignSeriesVars) =>
            apiClient.post(API_ENDPOINTS.SERIES_UNASSIGN, { path, names, source }),
        onMutate: ({ path, names }) => {
            const previousMeta = queryClient.getQueryData<BookMetaMap>(metaQueryKey(source));
            queryClient.setQueryData<BookMetaMap>(metaQueryKey(source), (prev = {}) => {
                const next = { ...prev };
                for (const name of names) {
                    const key = makeBookMetaKey(path, name);
                    const existing = next[key];
                    if (!existing) continue;
                    const {
                        series_id: _sid,
                        series_title: _st,
                        series_index: _si,
                        ...rest
                    } = existing;
                    next[key] = rest as BookMetaEntry;
                }
                return next;
            });
            return { previousMeta };
        },
        onError: (_err, _vars, context) => {
            if (context?.previousMeta !== undefined) {
                queryClient.setQueryData(metaQueryKey(source), context.previousMeta);
            }
        },
    });

    // ── reorderSeries ───────────────────────────────────────────────────────
    const { mutateAsync: mutateReorder } = useMutation({
        mutationFn: ({ path, names, seriesId }: ReorderSeriesVars) =>
            apiClient.post(API_ENDPOINTS.SERIES_REORDER, {
                path,
                names,
                series_id: seriesId,
                source,
            }),
        onMutate: ({ path, names }) => {
            // snapshot を updater 内で構築することで StrictMode の二重呼び出しに対応
            let snapshot: Record<string, number | undefined> = {};
            queryClient.setQueryData<BookMetaMap>(metaQueryKey(source), (prev = {}) => {
                snapshot = {};
                const next = { ...prev };
                names.forEach((name, i) => {
                    const key = makeBookMetaKey(path, name);
                    snapshot[key] = prev[key]?.series_index;
                    const existing = next[key];
                    if (!existing) return;
                    next[key] = { ...existing, series_index: i + 1 };
                });
                return next;
            });
            return { snapshot };
        },
        onError: (_err, _vars, context) => {
            if (!context?.snapshot) return;
            queryClient.setQueryData<BookMetaMap>(metaQueryKey(source), (prev = {}) => {
                const next = { ...prev };
                for (const [key, idx] of Object.entries(context.snapshot)) {
                    const existing = next[key];
                    if (!existing) continue;
                    if (idx === undefined) {
                        const { series_index: _si, ...rest } = existing;
                        next[key] = rest as BookMetaEntry;
                    } else {
                        next[key] = { ...existing, series_index: idx };
                    }
                }
                return next;
            });
        },
    });

    /**
     * 書籍を既存または新規シリーズに割り当てる。
     * - `id` 省略時はバックエンドで自動生成（同タイトル + 同作者なら同じ id）
     * - `index` は単一 number または names と同じ長さの number 配列
     * - 戻り値は確定した `series_id`
     */
    const assignSeries = useCallback(
        async (
            path: string,
            names: string[],
            params: { title: string; index: number | number[]; id?: string },
        ): Promise<string> => {
            if (Array.isArray(params.index) && params.index.length !== names.length) {
                throw new Error('index 配列の長さが names と一致しません');
            }
            const res = await mutateAssign({ path, names, params });
            return res.id;
        },
        [mutateAssign],
    );

    /** 書籍をシリーズから外す（series_* フィールドを削除）。 */
    const unassignSeries = useCallback(
        (path: string, names: string[]): Promise<void> =>
            mutateUnassign({ path, names }).then(() => undefined),
        [mutateUnassign],
    );

    /** シリーズドリルダウン中の DnD ドロップで呼ばれる。楽観的更新 + ロールバック実装済み。 */
    const reorderSeries = useCallback(
        (path: string, names: string[], seriesId: string): Promise<void> =>
            mutateReorder({ path, names, seriesId }).then(() => undefined),
        [mutateReorder],
    );

    return { assignSeries, unassignSeries, reorderSeries };
}
