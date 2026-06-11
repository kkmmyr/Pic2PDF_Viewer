/**
 * useNovelDbScope: URL ↔ state 同期のテスト。
 */
import { renderHook, act } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import type { ReactNode } from 'react';

import { useNovelDbScope } from '@/hooks/novel_db/useNovelDbScope';

function makeWrapper(initialEntries: string[]) {
    return function Wrapper({ children }: { children: ReactNode }) {
        return <MemoryRouter initialEntries={initialEntries}>{children}</MemoryRouter>;
    };
}

describe('useNovelDbScope', () => {
    it('URL に scope パラメータが無い場合は all を返す', () => {
        const { result } = renderHook(() => useNovelDbScope(), {
            wrapper: makeWrapper(['/novel-db']),
        });
        expect(result.current.scope).toEqual({ type: 'all' });
    });

    it('scope=series&series_id を解釈する', () => {
        const { result } = renderHook(() => useNovelDbScope(), {
            wrapper: makeWrapper(['/novel-db?scope=series&series_id=oko']),
        });
        expect(result.current.scope).toEqual({ type: 'series', id: 'oko' });
    });

    it('scope=book&book を解釈する', () => {
        const { result } = renderHook(() => useNovelDbScope(), {
            wrapper: makeWrapper(['/novel-db?scope=book&book=BookA']),
        });
        expect(result.current.scope).toEqual({ type: 'book', id: 'BookA' });
    });

    it('series_id が空のときは all にフォールバックする', () => {
        const { result } = renderHook(() => useNovelDbScope(), {
            wrapper: makeWrapper(['/novel-db?scope=series']),
        });
        expect(result.current.scope).toEqual({ type: 'all' });
    });

    it('setScope(book) で URL が更新される', () => {
        const { result } = renderHook(() => useNovelDbScope(), {
            wrapper: makeWrapper(['/novel-db']),
        });
        act(() => {
            result.current.setScope({ type: 'book', id: 'BookB' });
        });
        expect(result.current.scope).toEqual({ type: 'book', id: 'BookB' });
    });

    it('setScope(all) でパラメータが消える', () => {
        const { result } = renderHook(() => useNovelDbScope(), {
            wrapper: makeWrapper(['/novel-db?scope=book&book=X']),
        });
        act(() => {
            result.current.setScope({ type: 'all' });
        });
        expect(result.current.scope).toEqual({ type: 'all' });
    });
});
