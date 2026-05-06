import { renderHook, act } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { useUrlFilters } from '../hooks/useUrlFilters';

const wrapper =
    (initial: string) =>
    ({ children }: { children: React.ReactNode }) => (
        <MemoryRouter initialEntries={[initial]}>{children}</MemoryRouter>
    );

describe('useUrlFilters', () => {
    it('初期 URL クエリから author / tag / series が読み出される', () => {
        const { result } = renderHook(() => useUrlFilters(), {
            wrapper: wrapper('/?author=A&tag=T&series=S'),
        });
        expect(result.current.authorFilter).toBe('A');
        expect(result.current.tagFilter).toBe('T');
        expect(result.current.seriesFilter).toBe('S');
    });

    it('クエリ無しなら全部空文字', () => {
        const { result } = renderHook(() => useUrlFilters(), { wrapper: wrapper('/') });
        expect(result.current.authorFilter).toBe('');
        expect(result.current.tagFilter).toBe('');
        expect(result.current.seriesFilter).toBe('');
    });

    it('setAuthorFilter で URL に反映され getter が更新される', () => {
        const { result } = renderHook(() => useUrlFilters(), { wrapper: wrapper('/') });
        act(() => result.current.setAuthorFilter('サークルA'));
        expect(result.current.authorFilter).toBe('サークルA');
    });

    it('setTagFilter / setSeriesFilter も同様に反映', () => {
        const { result } = renderHook(() => useUrlFilters(), { wrapper: wrapper('/') });
        act(() => result.current.setTagFilter('TagX'));
        act(() => result.current.setSeriesFilter('SidY'));
        expect(result.current.tagFilter).toBe('TagX');
        expect(result.current.seriesFilter).toBe('SidY');
    });

    it('空文字を渡すとクエリから削除される（フィルタ解除）', () => {
        const { result } = renderHook(() => useUrlFilters(), {
            wrapper: wrapper('/?author=X'),
        });
        expect(result.current.authorFilter).toBe('X');
        act(() => result.current.setAuthorFilter(''));
        expect(result.current.authorFilter).toBe('');
    });

    it('他のクエリは保持される（author 設定で tag / series が消えない）', () => {
        const { result } = renderHook(() => useUrlFilters(), {
            wrapper: wrapper('/?tag=T&series=S'),
        });
        act(() => result.current.setAuthorFilter('A'));
        expect(result.current.authorFilter).toBe('A');
        expect(result.current.tagFilter).toBe('T');
        expect(result.current.seriesFilter).toBe('S');
    });

    it('clearAllDrilldown で author / series が消え、tag は残る', () => {
        const { result } = renderHook(() => useUrlFilters(), {
            wrapper: wrapper('/?author=A&tag=T&series=S'),
        });
        act(() => result.current.clearAllDrilldown());
        expect(result.current.authorFilter).toBe('');
        expect(result.current.seriesFilter).toBe('');
        expect(result.current.tagFilter).toBe('T'); // 維持
    });
});
