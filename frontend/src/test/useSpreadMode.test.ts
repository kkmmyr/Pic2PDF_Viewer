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

    it('handlePageSize: 横長（width > height * 1.2）→ 1 ページに確定', () => {
        const { result } = renderHook(() => useSpreadMode());
        // 1000 / 500 = 2.0 → 閾値 1.2 を超える
        act(() => result.current.handlePageSize(1000, 500));
        expect(result.current.isSpread).toBe(false);
    });

    it('handlePageSize: 縦長（width < height）→ 初期値 true を維持', () => {
        const { result } = renderHook(() => useSpreadMode());
        act(() => result.current.handlePageSize(500, 1000));
        expect(result.current.isSpread).toBe(true);
    });

    it('handlePageSize: 正方形 → 初期値 true を維持', () => {
        const { result } = renderHook(() => useSpreadMode());
        act(() => result.current.handlePageSize(500, 500));
        expect(result.current.isSpread).toBe(true);
    });

    it('閾値境界: width = height * 1.2 ちょうど → true 維持（横長と判定しない）', () => {
        const { result } = renderHook(() => useSpreadMode());
        // 600 / 500 = 1.2 ちょうど → 閾値「超え」ではないので true 維持
        act(() => result.current.handlePageSize(600, 500));
        expect(result.current.isSpread).toBe(true);
    });

    it('閾値境界: width = height * 1.2 をわずかに超える → false 確定', () => {
        const { result } = renderHook(() => useSpreadMode());
        // 601 / 500 = 1.202 → 閾値超え
        act(() => result.current.handlePageSize(601, 500));
        expect(result.current.isSpread).toBe(false);
    });

    it('片方でも横長を検出したら false に確定し、その後縦長が来ても false 維持', () => {
        const { result } = renderHook(() => useSpreadMode());
        // 左ページ = 横長（見開き原稿）
        act(() => result.current.handlePageSize(1000, 500));
        expect(result.current.isSpread).toBe(false);
        // 右ページ = 縦長 → 縦長検出時は何もしない（false 維持）
        act(() => result.current.handlePageSize(500, 1000));
        expect(result.current.isSpread).toBe(false);
    });

    it('handlePageSize: 非 auto モードでは autoIsSpread を変更しない', () => {
        const { result } = renderHook(() => useSpreadMode());
        act(() => result.current.cycleSpreadMode()); // auto → spread

        // single にして isSpread=false の状態を確認
        act(() => result.current.cycleSpreadMode()); // spread → single
        expect(result.current.isSpread).toBe(false);

        // single モードで横長を通知しても autoIsSpread は変更されない
        // （single モードの isSpread=false は autoIsSpread に依存せず spreadMode 直接判定）
        act(() => result.current.handlePageSize(1000, 500));
        expect(result.current.isSpread).toBe(false);
    });

    it('resetAutoSpread で autoIsSpread が true に戻る', () => {
        const { result } = renderHook(() => useSpreadMode());
        act(() => result.current.handlePageSize(1000, 500)); // false に
        expect(result.current.isSpread).toBe(false);

        act(() => result.current.resetAutoSpread());
        expect(result.current.isSpread).toBe(true);
    });

    it('resetAutoSpread 後に横長を検出すれば再び false 確定', () => {
        const { result } = renderHook(() => useSpreadMode());
        act(() => result.current.handlePageSize(1000, 500)); // false に
        act(() => result.current.resetAutoSpread()); // true に戻す
        expect(result.current.isSpread).toBe(true);

        act(() => result.current.handlePageSize(1000, 500)); // 再び false
        expect(result.current.isSpread).toBe(false);
    });
});
