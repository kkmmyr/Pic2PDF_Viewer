import { renderHook, act } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { useUrlState } from '../hooks/useUrlState';

const wrapper =
    (initial: string) =>
    ({ children }: { children: React.ReactNode }) => (
        <MemoryRouter initialEntries={[initial]}>{children}</MemoryRouter>
    );

describe('useUrlState', () => {
    it('初期 URL が空なら currentPath="" / selectedPdf=null / currentSource="generated"', () => {
        const { result } = renderHook(() => useUrlState(), { wrapper: wrapper('/') });
        expect(result.current.currentPath).toBe('');
        expect(result.current.selectedPdf).toBeNull();
        expect(result.current.currentSource).toBe('generated');
    });

    it('URL クエリから currentPath / selectedPdf / currentSource が読み出される', () => {
        const { result } = renderHook(() => useUrlState(), {
            wrapper: wrapper('/?path=sub&file=book.pdf&source=kindle'),
        });
        expect(result.current.currentPath).toBe('sub');
        expect(result.current.selectedPdf).toBe('book.pdf');
        expect(result.current.currentSource).toBe('kindle');
    });

    it('不正な source は generated にフォールバック', () => {
        const { result } = renderHook(() => useUrlState(), {
            wrapper: wrapper('/?source=invalid'),
        });
        expect(result.current.currentSource).toBe('generated');
    });

    it('navigateIntoFolder で path が "{base}/{dir}" に更新', () => {
        const { result } = renderHook(() => useUrlState(), { wrapper: wrapper('/') });
        act(() => result.current.navigateIntoFolder('sub', '', 'generated'));
        expect(result.current.currentPath).toBe('sub');
        expect(result.current.currentSource).toBe('generated');
    });

    it('navigateIntoFolder で base 配下にネスト', () => {
        const { result } = renderHook(() => useUrlState(), {
            wrapper: wrapper('/?path=sub'),
        });
        act(() => result.current.navigateIntoFolder('child', 'sub', 'generated'));
        expect(result.current.currentPath).toBe('sub/child');
    });

    it('navigateUp で 1 階層戻る', () => {
        const { result } = renderHook(() => useUrlState(), {
            wrapper: wrapper('/?path=a/b/c'),
        });
        act(() => result.current.navigateUp('a/b/c', 'generated'));
        expect(result.current.currentPath).toBe('a/b');
    });

    it('navigateUp: ルート（path=""）では何もしない', () => {
        const { result } = renderHook(() => useUrlState(), { wrapper: wrapper('/') });
        act(() => result.current.navigateUp('', 'generated'));
        expect(result.current.currentPath).toBe('');
    });

    it('navigateUp 後に source も保持される', () => {
        const { result } = renderHook(() => useUrlState(), {
            wrapper: wrapper('/?path=sub&source=kindle'),
        });
        act(() => result.current.navigateUp('sub', 'kindle'));
        expect(result.current.currentSource).toBe('kindle');
    });

    it('selectPdf で file が設定され、currentPath は維持', () => {
        const { result } = renderHook(() => useUrlState(), {
            wrapper: wrapper('/?path=sub'),
        });
        act(() => result.current.selectPdf('book.pdf', 'sub', 'generated'));
        expect(result.current.selectedPdf).toBe('book.pdf');
        expect(result.current.currentPath).toBe('sub');
    });

    it('clearPdf で file が消え、path と source は維持', () => {
        const { result } = renderHook(() => useUrlState(), {
            wrapper: wrapper('/?file=x.pdf&path=sub&source=kindle'),
        });
        act(() => result.current.clearPdf('sub', 'kindle'));
        expect(result.current.selectedPdf).toBeNull();
        expect(result.current.currentPath).toBe('sub');
        expect(result.current.currentSource).toBe('kindle');
    });

    it('setSource はソースだけ変更し path / file をリセット', () => {
        const { result } = renderHook(() => useUrlState(), {
            wrapper: wrapper('/?path=sub&file=x.pdf&source=generated'),
        });
        act(() => result.current.setSource('kindle'));
        expect(result.current.currentSource).toBe('kindle');
        expect(result.current.currentPath).toBe('');
        expect(result.current.selectedPdf).toBeNull();
    });
});
