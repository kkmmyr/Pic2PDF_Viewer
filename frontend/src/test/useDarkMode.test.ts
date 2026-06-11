import { renderHook, act } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { useDarkMode } from '@/hooks/useDarkMode';

const STORAGE_KEY = 'darkMode';

describe('useDarkMode', () => {
    beforeEach(() => {
        localStorage.clear();
        document.documentElement.classList.remove('dark');
        Object.defineProperty(window, 'matchMedia', {
            writable: true,
            configurable: true,
            value: vi.fn().mockReturnValue({ matches: false }),
        });
    });

    it('localStorage 空 + system light で isDark=false', () => {
        const { result } = renderHook(() => useDarkMode());
        expect(result.current.isDark).toBe(false);
        expect(document.documentElement.classList.contains('dark')).toBe(false);
    });

    it('localStorage="true" の場合 isDark=true で復元', () => {
        localStorage.setItem(STORAGE_KEY, 'true');
        const { result } = renderHook(() => useDarkMode());
        expect(result.current.isDark).toBe(true);
        expect(document.documentElement.classList.contains('dark')).toBe(true);
    });

    it('localStorage="false" の場合は false で復元（system が dark でも override）', () => {
        localStorage.setItem(STORAGE_KEY, 'false');
        Object.defineProperty(window, 'matchMedia', {
            writable: true,
            configurable: true,
            value: vi.fn().mockReturnValue({ matches: true }),
        });

        const { result } = renderHook(() => useDarkMode());
        expect(result.current.isDark).toBe(false);
    });

    it('localStorage 空 + system dark で isDark=true', () => {
        Object.defineProperty(window, 'matchMedia', {
            writable: true,
            configurable: true,
            value: vi.fn().mockReturnValue({ matches: true }),
        });

        const { result } = renderHook(() => useDarkMode());
        expect(result.current.isDark).toBe(true);
    });

    it('toggle で false ↔ true が切り替わり、html の dark クラスと localStorage が同期', () => {
        const { result } = renderHook(() => useDarkMode());
        expect(result.current.isDark).toBe(false);

        act(() => result.current.toggle());
        expect(result.current.isDark).toBe(true);
        expect(document.documentElement.classList.contains('dark')).toBe(true);
        expect(localStorage.getItem(STORAGE_KEY)).toBe('true');

        act(() => result.current.toggle());
        expect(result.current.isDark).toBe(false);
        expect(document.documentElement.classList.contains('dark')).toBe(false);
        expect(localStorage.getItem(STORAGE_KEY)).toBe('false');
    });

    it('matchMedia が throw しても fallback で false', () => {
        Object.defineProperty(window, 'matchMedia', {
            writable: true,
            configurable: true,
            value: vi.fn().mockImplementation(() => {
                throw new Error('not supported');
            }),
        });
        const { result } = renderHook(() => useDarkMode());
        expect(result.current.isDark).toBe(false);
    });
});
