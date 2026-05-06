import { renderHook, act } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { useSpreadMode } from '../hooks/useSpreadMode';

describe('useSpreadMode', () => {
    it('初期: spreadMode=auto / isSpread=true（autoIsSpread の初期値）', () => {
        const { result } = renderHook(() => useSpreadMode());
        expect(result.current.spreadMode).toBe('auto');
        expect(result.current.isSpread).toBe(true);
    });

    it('cycleSpreadMode: auto → spread → single → auto と循環', () => {
        const { result } = renderHook(() => useSpreadMode());
        act(() => result.current.cycleSpreadMode());
        expect(result.current.spreadMode).toBe('spread');
        act(() => result.current.cycleSpreadMode());
        expect(result.current.spreadMode).toBe('single');
        act(() => result.current.cycleSpreadMode());
        expect(result.current.spreadMode).toBe('auto');
    });

    it('spread モードでは isSpread=true', () => {
        const { result } = renderHook(() => useSpreadMode());
        act(() => result.current.cycleSpreadMode()); // auto → spread
        expect(result.current.isSpread).toBe(true);
    });

    it('single モードでは isSpread=false', () => {
        const { result } = renderHook(() => useSpreadMode());
        act(() => result.current.cycleSpreadMode()); // auto → spread
        act(() => result.current.cycleSpreadMode()); // spread → single
        expect(result.current.isSpread).toBe(false);
    });

    it('handlePageSize: auto モードで横長（width > height）→ 1ページ', () => {
        const { result } = renderHook(() => useSpreadMode());
        act(() => result.current.handlePageSize(1000, 500));
        expect(result.current.isSpread).toBe(false);
    });

    it('handlePageSize: auto モードで縦長（width <= height）→ 見開き', () => {
        const { result } = renderHook(() => useSpreadMode());
        act(() => result.current.handlePageSize(500, 1000));
        expect(result.current.isSpread).toBe(true);
    });

    it('handlePageSize: 正方形（width === height）→ 見開き', () => {
        const { result } = renderHook(() => useSpreadMode());
        act(() => result.current.handlePageSize(500, 500));
        expect(result.current.isSpread).toBe(true);
    });

    it('handlePageSize: 非 auto モードでは autoIsSpread を変更しない', () => {
        const { result } = renderHook(() => useSpreadMode());
        act(() => result.current.cycleSpreadMode()); // auto → spread

        // single にして isSpread=false の状態を確認
        act(() => result.current.cycleSpreadMode()); // spread → single
        expect(result.current.isSpread).toBe(false);

        // single モードで handlePageSize を呼んでも isSpread は false のまま
        act(() => result.current.handlePageSize(500, 1000));
        expect(result.current.isSpread).toBe(false);
    });

    it('resetAutoSpread で autoIsSpread が true に戻る', () => {
        const { result } = renderHook(() => useSpreadMode());
        act(() => result.current.handlePageSize(1000, 500)); // false に
        expect(result.current.isSpread).toBe(false);

        act(() => result.current.resetAutoSpread());
        expect(result.current.isSpread).toBe(true);
    });
});
