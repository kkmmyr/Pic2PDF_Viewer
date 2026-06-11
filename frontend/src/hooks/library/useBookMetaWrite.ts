import { useCallback } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import type { BookMetaEntry, BookMetaMap, ReadState } from '../../types';
import { API_ENDPOINTS } from '../../config/api';
import apiClient from '../../config/api_client';
import { metaQueryKey, makeBookMetaKey } from './useBookMetaCore';

interface UpdateMetaVars {
    path: string;
    names: string[];
    fields: {
        authors?: string[];
        hidden?: boolean;
        genre?: string;
        read_state?: ReadState | '';
    };
}

/** キャッシュに対してフィールドをマージする純粋関数（onMutate / onSuccess 共用）。 */
function applyMetaFields(prev: BookMetaMap, { path, names, fields }: UpdateMetaVars): BookMetaMap {
    const next = { ...prev };
    for (const name of names) {
        const key = makeBookMetaKey(path, name);
        const existing = next[key] ?? { authors: [] };
        const merged: BookMetaEntry = { ...existing };

        if (fields.authors !== undefined) merged.authors = fields.authors;
        if (fields.hidden !== undefined) {
            if (fields.hidden) merged.hidden = true;
            else delete merged.hidden;
        }
        if (fields.genre !== undefined) {
            if (fields.genre) merged.genre = fields.genre;
            else delete merged.genre;
        }
        if (fields.read_state !== undefined) {
            if (fields.read_state === '') delete merged.read_state;
            else merged.read_state = fields.read_state;
        }

        const isEmptyArray = (v: unknown): boolean => Array.isArray(v) && v.length === 0;
        const hasNonEmpty = Object.entries(merged).some(([, v]) => !isEmptyArray(v));

        if (hasNonEmpty) next[key] = merged;
        else delete next[key];
    }
    return next;
}

/**
 * 書籍メタデータ（authors / hidden / genre / read_state）の書き込み系フック。
 *
 * PATCH /api/meta を楽観的に実行し、失敗時はキャッシュをロールバックする。
 */
export function useBookMetaWrite(source: string) {
    const queryClient = useQueryClient();

    const { mutateAsync } = useMutation({
        mutationFn: async ({ path, names, fields }: UpdateMetaVars) => {
            await apiClient.patch(API_ENDPOINTS.META, {
                path,
                names,
                ...(fields.authors !== undefined ? { authors: fields.authors } : {}),
                ...(fields.hidden !== undefined ? { hidden: fields.hidden } : {}),
                ...(fields.genre !== undefined ? { genre: fields.genre } : {}),
                ...(fields.read_state !== undefined ? { read_state: fields.read_state } : {}),
                source,
            });
        },
        onMutate: (vars) => {
            const previousMeta = queryClient.getQueryData<BookMetaMap>(metaQueryKey(source));
            queryClient.setQueryData<BookMetaMap>(metaQueryKey(source), (prev = {}) =>
                applyMetaFields(prev, vars),
            );
            return { previousMeta };
        },
        onError: (_err, _vars, context) => {
            if (context?.previousMeta !== undefined) {
                queryClient.setQueryData(metaQueryKey(source), context.previousMeta);
            }
        },
    });

    const updateMeta = useCallback(
        async (path: string, names: string[], fields: UpdateMetaVars['fields']) => {
            if (
                fields.authors === undefined &&
                fields.hidden === undefined &&
                fields.genre === undefined &&
                fields.read_state === undefined
            )
                return;
            await mutateAsync({ path, names, fields });
        },
        [mutateAsync],
    );

    const updateAuthors = useCallback(
        (path: string, names: string[], authors: string[]) => updateMeta(path, names, { authors }),
        [updateMeta],
    );

    const updateGenre = useCallback(
        (path: string, names: string[], genre: string) => updateMeta(path, names, { genre }),
        [updateMeta],
    );

    const setHidden = useCallback(
        (path: string, names: string[], hidden: boolean) => updateMeta(path, names, { hidden }),
        [updateMeta],
    );

    const setReadState = useCallback(
        (path: string, names: string[], state: ReadState | '') =>
            updateMeta(path, names, { read_state: state }),
        [updateMeta],
    );

    return { updateMeta, updateAuthors, updateGenre, setHidden, setReadState };
}
