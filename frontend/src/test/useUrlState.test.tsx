import { renderHook, act } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { useUrlState } from '../hooks/library/useUrlState';
import { useUrlFilters } from '../hooks/library/useUrlFilters';

const wrapper =
    (initial: string) =>
    ({ children }: { children: React.ReactNode }) => (
        <MemoryRouter initialEntries={[initial]}>{children}</MemoryRouter>
    );

describe('useUrlState', () => {
    it('初期 URL が空なら currentPath="" / selectedPdf=null', () => {
        const { result } = renderHook(() => useUrlState(), { wrapper: wrapper('/') });
        expect(result.current.currentPath).toBe('');
        expect(result.current.selectedPdf).toBeNull();
    });

    it('URL クエリから currentPath / selectedPdf が読み出される', () => {
        const { result } = renderHook(() => useUrlState(), {
            wrapper: wrapper('/?path=sub&file=book.pdf'),
        });
        expect(result.current.currentPath).toBe('sub');
        expect(result.current.selectedPdf).toBe('book.pdf');
    });

    it('navigateIntoFolder で path が "{base}/{dir}" に更新', () => {
        const { result } = renderHook(() => useUrlState(), { wrapper: wrapper('/') });
        act(() => result.current.navigateIntoFolder('sub', ''));
        expect(result.current.currentPath).toBe('sub');
    });

    it('navigateIntoFolder で base 配下にネスト', () => {
        const { result } = renderHook(() => useUrlState(), {
            wrapper: wrapper('/?path=sub'),
        });
        act(() => result.current.navigateIntoFolder('child', 'sub'));
        expect(result.current.currentPath).toBe('sub/child');
    });

    it('navigateUp で 1 階層戻る', () => {
        const { result } = renderHook(() => useUrlState(), {
            wrapper: wrapper('/?path=a/b/c'),
        });
        act(() => result.current.navigateUp('a/b/c'));
        expect(result.current.currentPath).toBe('a/b');
    });

    it('navigateUp: ルート（path=""）では何もしない', () => {
        const { result } = renderHook(() => useUrlState(), { wrapper: wrapper('/') });
        act(() => result.current.navigateUp(''));
        expect(result.current.currentPath).toBe('');
    });

    it('selectPdf で file が設定され、currentPath は維持', () => {
        const { result } = renderHook(() => useUrlState(), {
            wrapper: wrapper('/?path=sub'),
        });
        act(() => result.current.selectPdf('book.pdf', 'sub'));
        expect(result.current.selectedPdf).toBe('book.pdf');
        expect(result.current.currentPath).toBe('sub');
    });

    it('selectPdf で author / series フィルターが保持される', () => {
        const { result } = renderHook(
            () => ({ url: useUrlState(), filters: useUrlFilters() }),
            { wrapper: wrapper('/?path=sub&author=foo&series=bar') },
        );
        act(() => result.current.url.selectPdf('book.pdf', 'sub'));
        expect(result.current.url.selectedPdf).toBe('book.pdf');
        expect(result.current.filters.authorFilter).toBe('foo');
        expect(result.current.filters.seriesFilter).toBe('bar');
    });

    it('clearPdf で file が消え、path は維持', () => {
        const { result } = renderHook(() => useUrlState(), {
            wrapper: wrapper('/?file=x.pdf&path=sub'),
        });
        act(() => result.current.clearPdf());
        expect(result.current.selectedPdf).toBeNull();
        expect(result.current.currentPath).toBe('sub');
    });

    it('clearPdf で author / series フィルターが保持される', () => {
        const { result } = renderHook(() => useUrlState(), {
            wrapper: wrapper('/?file=x.pdf&path=sub&author=foo&series=bar'),
        });
        act(() => result.current.clearPdf());
        expect(result.current.selectedPdf).toBeNull();
        expect(result.current.currentPath).toBe('sub');
    });
});
