import { useState, useEffect, useCallback } from 'react';
import type { BookMetaMap, BookMetaEntry } from '../types';
import { API_ENDPOINTS } from '../config/api';
import apiClient from '../config/api_client';
import { useMetaDerived } from './useMetaDerived';

/**
 * 書籍メタデータ（作者名）を管理するフック。
 *
 * - source が変わると meta.json を再取得する。
 * - updateAuthors で1冊または複数冊の作者名を一括更新する。
 * - getAuthors でキー（path + name）から作者名リストを取得する。
 * - allAuthors でこのソースに登録されている全作者名の重複排除リストを返す。
 */
export function useBookMeta(source: string) {
    const [meta, setMeta] = useState<BookMetaMap>({});

    const fetchMeta = useCallback(async () => {
        try {
            const data = await apiClient.get<unknown, BookMetaMap>(
                API_ENDPOINTS.META,
                { params: { source } }
            );
            setMeta(data ?? {});
        } catch {
            setMeta({});
        }
    }, [source]);

    useEffect(() => {
        fetchMeta();
    }, [fetchMeta]);

    /** path + name からメタキーを生成する */
    const makeKey = useCallback((path: string, name: string) => {
        return path ? `${path}/${name}` : name;
    }, []);

    /** 1冊の作者名リストを返す */
    const getAuthors = useCallback((path: string, name: string): string[] => {
        return meta[makeKey(path, name)]?.authors ?? [];
    }, [meta, makeKey]);

    /** 1冊のタグリストを返す */
    const getTags = useCallback((path: string, name: string): string[] => {
        return meta[makeKey(path, name)]?.tags ?? [];
    }, [meta, makeKey]);

    /** 1冊のシリーズ情報を返す（未割当なら null） */
    const getSeries = useCallback((path: string, name: string): { id: string; title: string; index: number } | null => {
        const e = meta[makeKey(path, name)];
        if (!e?.series_id) return null;
        return {
            id: e.series_id,
            title: e.series_title ?? '',
            index: e.series_index ?? 0,
        };
    }, [meta, makeKey]);

    /** 1冊が非表示状態かを返す */
    const isHidden = useCallback((path: string, name: string): boolean => {
        return meta[makeKey(path, name)]?.hidden === true;
    }, [meta, makeKey]);

    /** 1冊の閲覧回数を返す（未記録は 0） */
    const getViewCount = useCallback((path: string, name: string): number => {
        return meta[makeKey(path, name)]?.view_count ?? 0;
    }, [meta, makeKey]);

    /** 1冊の最終閲覧時刻 (UNIX 秒) を返す（未閲覧は undefined） */
    const getLastViewedAt = useCallback((path: string, name: string): number | undefined => {
        return meta[makeKey(path, name)]?.last_viewed_at;
    }, [meta, makeKey]);

    /** 閲覧を記録（カウント +1、UI には反映されるが失敗時は黙ってスキップ） */
    const recordView = useCallback(async (path: string, name: string): Promise<void> => {
        try {
            const res = await apiClient.post<unknown, { view_count: number; last_viewed_at: number }>(
                API_ENDPOINTS.META_VIEW,
                { path, name, source }
            );
            setMeta(prev => {
                const key = makeKey(path, name);
                const existing = prev[key] ?? { authors: [] };
                return {
                    ...prev,
                    [key]: {
                        ...existing,
                        view_count: res.view_count,
                        last_viewed_at: res.last_viewed_at,
                    },
                };
            });
        } catch {
            // 閲覧記録の失敗はユーザー体験に影響しないので握りつぶす
        }
    }, [source, makeKey]);

    /**
     * 1冊または複数冊のメタデータ（authors / tags / hidden）を上書き保存する。
     * 指定されたフィールドのみ変更され、他のフィールドは保持される。
     */
    const updateMeta = useCallback(async (
        path: string,
        names: string[],
        fields: { authors?: string[]; tags?: string[]; hidden?: boolean; genre?: string }
    ) => {
        if (fields.authors === undefined && fields.tags === undefined && fields.hidden === undefined && fields.genre === undefined) return;

        await apiClient.patch(API_ENDPOINTS.META, {
            path,
            names,
            ...(fields.authors !== undefined ? { authors: fields.authors } : {}),
            ...(fields.tags !== undefined ? { tags: fields.tags } : {}),
            ...(fields.hidden !== undefined ? { hidden: fields.hidden } : {}),
            ...(fields.genre !== undefined ? { genre: fields.genre } : {}),
            source,
        });

        // ローカル状態を即時更新。バックエンドのマージ規則に合わせて、
        // 指定されたフィールドのみ書き換え、他フィールドは保持。
        setMeta(prev => {
            const next = { ...prev };
            for (const name of names) {
                const key = makeKey(path, name);
                const existing = next[key] ?? { authors: [] };
                const merged: BookMetaEntry = { ...existing };

                if (fields.authors !== undefined) merged.authors = fields.authors;
                if (fields.tags !== undefined) merged.tags = fields.tags;
                if (fields.hidden !== undefined) {
                    if (fields.hidden) {
                        merged.hidden = true;
                    } else {
                        delete merged.hidden;
                    }
                }
                if (fields.genre !== undefined) {
                    if (fields.genre) {
                        merged.genre = fields.genre;
                    } else {
                        delete merged.genre;
                    }
                }

                // 空配列フィールドを除外して、意味のある値が残るか判定
                const isEmptyArray = (v: unknown): boolean => Array.isArray(v) && v.length === 0;
                const hasNonEmpty = Object.entries(merged).some(([_, v]) => !isEmptyArray(v));

                if (hasNonEmpty) {
                    next[key] = merged;
                } else {
                    delete next[key];
                }
            }
            return next;
        });
    }, [source, makeKey]);

    /** 後方互換: authors のみを更新する旧 API。内部で updateMeta に委譲。 */
    const updateAuthors = useCallback((path: string, names: string[], authors: string[]) => {
        return updateMeta(path, names, { authors });
    }, [updateMeta]);

    /** タグのみを更新する。 */
    const updateTags = useCallback((path: string, names: string[], tags: string[]) => {
        return updateMeta(path, names, { tags });
    }, [updateMeta]);

    /** ジャンルのみを更新する。 */
    const updateGenre = useCallback((path: string, names: string[], genre: string) => {
        return updateMeta(path, names, { genre });
    }, [updateMeta]);

    /** 非表示フラグを更新する。`hidden=true` で非表示化、`false` で再表示。 */
    const setHidden = useCallback((path: string, names: string[], hidden: boolean) => {
        return updateMeta(path, names, { hidden });
    }, [updateMeta]);

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
        // index 配列のときは長さチェック
        if (Array.isArray(params.index) && params.index.length !== names.length) {
            throw new Error('index 配列の長さが names と一致しません');
        }

        const res = await apiClient.post<unknown, { id: string; updated_count: number }>(
            API_ENDPOINTS.SERIES_ASSIGN,
            { path, names, ...params, source }
        );
        const sid = res.id;

        // ローカル状態を即時更新（index が配列なら name ごとに個別に当てる）
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
    }, [source, makeKey]);

    /**
     * 同じシリーズに属する書籍の `series_index` を `names` の順序で
     * 1.0, 2.0, 3.0, ... に振り直す（DnD 並べ替え用）。
     *
     * 楽観的更新: ローカル meta を即時に書き換えてから API を投げ、
     * 失敗時はスナップショットからロールバックする（ドロップ時に
     * カードが元位置に戻ってチラつかないようにするため）。
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
    }, [source, makeKey]);

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
    }, [source, makeKey]);

    const { allAuthors, allTags, allGenres, allSeries, allSeriesWithStats } = useMetaDerived(meta);

    return {
        meta,
        getAuthors, getTags, getSeries, getViewCount, getLastViewedAt, isHidden,
        recordView,
        updateAuthors, updateTags, updateMeta, updateGenre, setHidden,
        assignSeries, unassignSeries, reorderSeries,
        allAuthors, allTags, allGenres, allSeries, allSeriesWithStats,
        refreshMeta: fetchMeta,
    };
}
