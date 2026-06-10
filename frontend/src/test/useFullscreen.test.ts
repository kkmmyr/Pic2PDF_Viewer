import { renderHook, act } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import { useFullscreen } from '../hooks/reader/useFullscreen';

describe('useFullscreen', () => {
    let requestSpy: ReturnType<typeof vi.fn>;
    let exitSpy: ReturnType<typeof vi.fn>;
    let originalRequest: unknown;
    let originalExit: unknown;

    beforeEach(() => {
        // jsdom には fullscreen API が無いため、簡易 mock を差し込む
        originalRequest = (Element.prototype as unknown as { requestFullscreen?: unknown })
            .requestFullscreen;
        originalExit = (document as unknown as { exitFullscreen?: unknown }).exitFullscreen;

        requestSpy = vi.fn().mockResolvedValue(undefined);
        exitSpy = vi.fn().mockResolvedValue(undefined);

        Element.prototype.requestFullscreen = requestSpy as unknown as Element['requestFullscreen'];
        document.exitFullscreen = exitSpy as unknown as Document['exitFullscreen'];

        Object.defineProperty(document, 'fullscreenElement', {
            configurable: true,
            value: null,
        });
    });

    afterEach(() => {
        Element.prototype.requestFullscreen =
            originalRequest as unknown as Element['requestFullscreen'];
        document.exitFullscreen = originalExit as unknown as Document['exitFullscreen'];
    });

    it('初期 isFullscreen=false（fullscreenElement=null）', () => {
        const { result } = renderHook(() => useFullscreen());
        expect(result.current.isFullscreen).toBe(false);
    });

    it('toggleFullscreen: 通常時は requestFullscreen が呼ばれる', async () => {
        const { result } = renderHook(() => useFullscreen());
        await act(async () => {
            await result.current.toggleFullscreen();
        });
        expect(requestSpy).toHaveBeenCalled();
        expect(exitSpy).not.toHaveBeenCalled();
    });

    it('toggleFullscreen: フルスクリーン中なら exitFullscreen が呼ばれる', async () => {
        Object.defineProperty(document, 'fullscreenElement', {
            configurable: true,
            value: document.documentElement,
        });

        const { result } = renderHook(() => useFullscreen());
        await act(async () => {
            await result.current.toggleFullscreen();
        });
        expect(exitSpy).toHaveBeenCalled();
        expect(requestSpy).not.toHaveBeenCalled();
    });

    it('requestFullscreen が reject されても throw しない', async () => {
        requestSpy.mockRejectedValue(new Error('user denied'));
        const { result } = renderHook(() => useFullscreen());
        await act(async () => {
            await expect(result.current.toggleFullscreen()).resolves.toBeUndefined();
        });
    });

    it('fullscreenchange イベントで isFullscreen が更新される', () => {
        const { result } = renderHook(() => useFullscreen());

        Object.defineProperty(document, 'fullscreenElement', {
            configurable: true,
            value: document.documentElement,
        });

        act(() => {
            document.dispatchEvent(new Event('fullscreenchange'));
        });
        expect(result.current.isFullscreen).toBe(true);

        Object.defineProperty(document, 'fullscreenElement', {
            configurable: true,
            value: null,
        });
        act(() => {
            document.dispatchEvent(new Event('fullscreenchange'));
        });
        expect(result.current.isFullscreen).toBe(false);
    });
});
