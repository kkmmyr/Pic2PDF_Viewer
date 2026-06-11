/**
 * URL クエリパラメータと React state を双方向同期する scope フック。
 *
 * URL 仕様:
 *   - `scope=all` (default、`scope` 未指定でも all)
 *   - `scope=series&series_id=...`
 *   - `scope=book&book=...`
 */
import { useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';

import type { Scope } from '@/features/novel_db/types';

export interface UseNovelDbScope {
    scope: Scope;
    setScope: (next: Scope) => void;
}

export function useNovelDbScope(): UseNovelDbScope {
    const [params, setParams] = useSearchParams();

    const scope: Scope = useMemo(() => {
        const type = params.get('scope');
        if (type === 'series') {
            const id = params.get('series_id');
            if (id) return { type: 'series', id };
        }
        if (type === 'book') {
            const id = params.get('book');
            if (id) return { type: 'book', id };
        }
        return { type: 'all' };
    }, [params]);

    const setScope = useCallback(
        (next: Scope) => {
            setParams(
                (prev) => {
                    const sp = new URLSearchParams(prev);
                    sp.delete('scope');
                    sp.delete('series_id');
                    sp.delete('book');
                    if (next.type === 'series' && next.id) {
                        sp.set('scope', 'series');
                        sp.set('series_id', next.id);
                    } else if (next.type === 'book' && next.id) {
                        sp.set('scope', 'book');
                        sp.set('book', next.id);
                    }
                    return sp;
                },
                { replace: true },
            );
        },
        [setParams],
    );

    return { scope, setScope };
}
