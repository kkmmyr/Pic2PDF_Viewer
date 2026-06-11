import { renderHook, act } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { useWindowSize } from '@/hooks/useWindowSize';

describe('useWindowSize', () => {
    it('初期値は window.innerWidth / innerHeight', () => {
        const { result } = renderHook(() => useWindowSize());
        expect(result.current.width).toBe(window.innerWidth);
        expect(result.current.height).toBe(window.innerHeight);
    });

    it('resize イベントで state が更新される', () => {
        const { result } = renderHook(() => useWindowSize());

        Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1024 });
        Object.defineProperty(window, 'innerHeight', { configurable: true, value: 768 });

        act(() => {
            window.dispatchEvent(new Event('resize'));
        });

        expect(result.current.width).toBe(1024);
        expect(result.current.height).toBe(768);
    });

    it('連続 resize で最新値が反映', () => {
        const { result } = renderHook(() => useWindowSize());

        Object.defineProperty(window, 'innerWidth', { configurable: true, value: 800 });
        Object.defineProperty(window, 'innerHeight', { configurable: true, value: 600 });
        act(() => window.dispatchEvent(new Event('resize')));
        expect(result.current.width).toBe(800);

        Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1280 });
        Object.defineProperty(window, 'innerHeight', { configurable: true, value: 720 });
        act(() => window.dispatchEvent(new Event('resize')));
        expect(result.current.width).toBe(1280);
        expect(result.current.height).toBe(720);
    });
});
