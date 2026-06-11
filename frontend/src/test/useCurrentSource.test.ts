import { renderHook } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';

vi.mock('react-router-dom', () => ({
    useLocation: vi.fn(),
}));

import { useLocation } from 'react-router-dom';
import { useCurrentSource } from '@/hooks/useCurrentSource';

const mockedUseLocation = useLocation as ReturnType<typeof vi.fn>;

describe('useCurrentSource', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it('/comic で始まるパスは "comic" を返す', () => {
        mockedUseLocation.mockReturnValue({ pathname: '/comic/book.pdf' });
        const { result } = renderHook(() => useCurrentSource());
        expect(result.current).toBe('comic');
    });

    it('/novel で始まるパスは "novel" を返す', () => {
        mockedUseLocation.mockReturnValue({ pathname: '/novel/book.pdf' });
        const { result } = renderHook(() => useCurrentSource());
        expect(result.current).toBe('novel');
    });

    it('/ のみ → "doujin" を返す', () => {
        mockedUseLocation.mockReturnValue({ pathname: '/' });
        const { result } = renderHook(() => useCurrentSource());
        expect(result.current).toBe('doujin');
    });

    it('/doujin で始まるパスも "doujin" を返す', () => {
        mockedUseLocation.mockReturnValue({ pathname: '/doujin/book.pdf' });
        const { result } = renderHook(() => useCurrentSource());
        expect(result.current).toBe('doujin');
    });
});
