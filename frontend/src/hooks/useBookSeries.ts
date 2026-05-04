import { useCallback } from 'react';
import type { BookMetaEntry } from '../types';
import { API_ENDPOINTS } from '../config/api';
import apiClient from '../config/api_client';
import type { SetBookMeta, MakeBookMetaKey } from './useBookMetaCore';

/**
 * シリーズ手動編集系フック（割り当て / 解除 / DnD 並べ替え）。
 *
 * `reorderSeries` は楽観的更新 + 失敗時ロールバック実装（StrictMode で
 * updater が 2 度呼ばれてもスナップショットを毎回再構築する）。
 */
export function useBookSeries(
    source: string,
    setMeta: SetBookMeta,
    makeKey: MakeBookMetaKey,
) {
    /**
     * 書籍を既存または新規シリーズに割り当てる。
     * - `id` 省略時はバックエンドで自動生成（同タイトル + 同作者なら同じ id）
     * - `index` は単一 number または names と同じ長さの number 配列
     * - 戻り値は確定した `series_id`
     */
    const assignSeries = useCallback(async (
        path: string,
        names: string[],
        params: { title: string; index: number | number[]; id?: string }
    ): Promise<string> => {
        if (Array.isArray(params.index) && params.index.length !== names.length) {
            throw new Error('index 配列の長さが names と一致しません');
        }

        const res = await apiClient.post<unknown, { id: string; updated_count: number }>(
            API_ENDPOINTS.SERIES_ASSIGN,
            { path, names, ...params, source }
        );
        const sid = res.id;

        const indexFor = (i: number): number =>
            Array.isArray(params.index) ? params.index[i] : params.index;

        setMeta(prev => {
            const next = { ...prev };
            names.forEach((name, i) => {
                const key = makeKey(path, name);
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
        return sid;
    }, [source, setMeta, makeKey]);

    /** 書籍をシリーズから外す（series_* フィールドを削除）。 */
    const unassignSeries = useCallback(async (path: string, names: string[]): Promise<void> => {
        await apiClient.post(API_ENDPOINTS.SERIES_UNASSIGN, { path, names, source });
        setMeta(prev => {
            const next = { ...prev };
            for (const name of names) {
                const key = makeKey(path, name);
                const existing = next[key];
                if (!existing) continue;
                const { series_id: _sid, series_title: _st, series_index: _si, ...rest } = existing;
                next[key] = rest as BookMetaEntry;
            }
            return next;
        });
    }, [source, setMeta, makeKey]);

    /**
     * 同じシリーズに属する書籍の `series_index` を `names` の順序で
     * 1.0, 2.0, 3.0, ... に振り直す（DnD 並べ替え用）。
     *
     * 楽観的更新: ローカル meta を即時に書き換えてから API を投げ、
     * 失敗時はスナップショットからロールバックする。
     */
    const reorderSeries = useCallback(async (
        path: string,
        names: string[],
        seriesId: string,
    ): Promise<void> => {
        // 楽観的更新と同時に rollback 用のスナップショットを取る。
        // StrictMode で updater が 2 回呼ばれても結果が同じになるよう毎回再構築する。
        let snapshot: Record<string, number | undefined> = {};
        setMeta(prev => {
            snapshot = {};
            const next = { ...prev };
            names.forEach((name, i) => {
                const key = makeKey(path, name);
                snapshot[key] = prev[key]?.series_index;
                const existing = next[key];
                if (!existing) return;
                next[key] = { ...existing, series_index: i + 1 };
            });
            return next;
        });

        try {
            await apiClient.post(API_ENDPOINTS.SERIES_REORDER, {
                path, names, series_id: seriesId, source,
            });
        } catch (e) {
            setMeta(prev => {
                const next = { ...prev };
                for (const [key, idx] of Object.entries(snapshot)) {
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
            throw e;
        }
    }, [source, setMeta, makeKey]);

    return { assignSeries, unassignSeries, reorderSeries };
}
