import { useState, useEffect, useCallback } from 'react';
import type { BookMetaMap, BookMetaEntry } from '../types';
import { API_ENDPOINTS } from '../config/api';
import apiClient from '../config/api_client';

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
     * 1冊または複数冊の作者名 / タグを上書き保存する。
     * `authors` / `tags` のどちらか（または両方）を指定する。省略したフィールドは変更されない。
     */
    const updateMeta = useCallback(async (
        path: string,
        names: string[],
        fields: { authors?: string[]; tags?: string[] }
    ) => {
        if (fields.authors === undefined && fields.tags === undefined) return;

        await apiClient.patch(API_ENDPOINTS.META, {
            path,
            names,
            ...(fields.authors !== undefined ? { authors: fields.authors } : {}),
            ...(fields.tags !== undefined ? { tags: fields.tags } : {}),
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

                // 空配列のフィールドを除外して、残るフィールドが無ければエントリごと削除
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

    /** このソースに登録されている全作者名（重複排除・ソート済み）*/
    const allAuthors: string[] = [...new Set(
        Object.values(meta).flatMap(e => e.authors)
    )].sort((a, b) => a.localeCompare(b, 'ja'));

    /** このソースに登録されている全タグ（重複排除・ソート済み）*/
    const allTags: string[] = [...new Set(
        Object.values(meta).flatMap(e => e.tags ?? [])
    )].sort((a, b) => a.localeCompare(b, 'ja'));

    return {
        meta,
        getAuthors, getTags, getViewCount, getLastViewedAt,
        recordView,
        updateAuthors, updateTags, updateMeta,
        allAuthors, allTags,
        refreshMeta: fetchMeta,
    };
}
