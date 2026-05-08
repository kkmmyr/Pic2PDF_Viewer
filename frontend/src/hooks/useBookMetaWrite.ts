import { useCallback } from 'react';
import type { BookMetaEntry, ReadState } from '../types';
import { API_ENDPOINTS } from '../config/api';
import apiClient from '../config/api_client';
import type { SetBookMeta, MakeBookMetaKey } from './useBookMetaCore';

/**
 * 書籍メタデータ（authors / hidden / genre / read_state）の書き込み系フック。
 *
 * `useBookMetaCore` から `setMeta` / `makeKey` を受け取り、PATCH /api/meta に
 * 送信した上でローカル状態をバックエンドのマージ規則に合わせて即時更新する。
 */
export function useBookMetaWrite(source: string, setMeta: SetBookMeta, makeKey: MakeBookMetaKey) {
    const updateMeta = useCallback(
        async (
            path: string,
            names: string[],
            fields: {
                authors?: string[];
                hidden?: boolean;
                genre?: string;
                /** 'unread' | 'reading' | 'done' | '' （空文字でクリア＝派生に戻す） */
                read_state?: ReadState | '';
            },
        ) => {
            if (
                fields.authors === undefined &&
                fields.hidden === undefined &&
                fields.genre === undefined &&
                fields.read_state === undefined
            )
                return;

            await apiClient.patch(API_ENDPOINTS.META, {
                path,
                names,
                ...(fields.authors !== undefined ? { authors: fields.authors } : {}),
                ...(fields.hidden !== undefined ? { hidden: fields.hidden } : {}),
                ...(fields.genre !== undefined ? { genre: fields.genre } : {}),
                ...(fields.read_state !== undefined ? { read_state: fields.read_state } : {}),
                source,
            });

            // ローカル状態を即時更新。バックエンドのマージ規則に合わせて、
            // 指定されたフィールドのみ書き換え、他フィールドは保持する。
            setMeta((prev) => {
                const next = { ...prev };
                for (const name of names) {
                    const key = makeKey(path, name);
                    const existing = next[key] ?? { authors: [] };
                    const merged: BookMetaEntry = { ...existing };

                    if (fields.authors !== undefined) merged.authors = fields.authors;
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
                    if (fields.read_state !== undefined) {
                        if (fields.read_state === '') {
                            delete merged.read_state;
                        } else {
                            merged.read_state = fields.read_state;
                        }
                    }

                    // 空配列フィールドを除外して、意味のある値が残るか判定
                    const isEmptyArray = (v: unknown): boolean =>
                        Array.isArray(v) && v.length === 0;
                    const hasNonEmpty = Object.entries(merged).some(([_, v]) => !isEmptyArray(v));

                    if (hasNonEmpty) {
                        next[key] = merged;
                    } else {
                        delete next[key];
                    }
                }
                return next;
            });
        },
        [source, setMeta, makeKey],
    );

    const updateAuthors = useCallback(
        (path: string, names: string[], authors: string[]) => {
            return updateMeta(path, names, { authors });
        },
        [updateMeta],
    );

    const updateGenre = useCallback(
        (path: string, names: string[], genre: string) => {
            return updateMeta(path, names, { genre });
        },
        [updateMeta],
    );

    const setHidden = useCallback(
        (path: string, names: string[], hidden: boolean) => {
            return updateMeta(path, names, { hidden });
        },
        [updateMeta],
    );

    const setReadState = useCallback(
        (path: string, names: string[], state: ReadState | '') => {
            return updateMeta(path, names, { read_state: state });
        },
        [updateMeta],
    );

    return { updateMeta, updateAuthors, updateGenre, setHidden, setReadState };
}
