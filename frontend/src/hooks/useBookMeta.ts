import { useState, useEffect, useCallback } from 'react';
import type { BookMetaMap } from '../types';
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

    /**
     * 1冊または複数冊の作者名を上書き保存する。
     * names に複数のファイル名を渡すと一括更新。
     */
    const updateAuthors = useCallback(async (
        path: string,
        names: string[],
        authors: string[]
    ) => {
        await apiClient.patch(API_ENDPOINTS.META, {
            path,
            names,
            authors,
            source,
        });
        // ローカル状態も即時更新（再フェッチを待たずに反映）
        setMeta(prev => {
            const next = { ...prev };
            for (const name of names) {
                const key = makeKey(path, name);
                if (authors.length > 0) {
                    next[key] = { authors };
                } else {
                    delete next[key];
                }
            }
            return next;
        });
    }, [source, makeKey]);

    /** このソースに登録されている全作者名（重複排除・ソート済み）*/
    const allAuthors: string[] = [...new Set(
        Object.values(meta).flatMap(e => e.authors)
    )].sort((a, b) => a.localeCompare(b, 'ja'));

    return { meta, getAuthors, updateAuthors, allAuthors, refreshMeta: fetchMeta };
}
