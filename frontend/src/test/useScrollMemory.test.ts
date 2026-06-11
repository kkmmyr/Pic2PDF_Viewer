import { renderHook, act } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import { useScrollMemory } from '@/hooks/library/useScrollMemory';

describe('useScrollMemory', () => {
    let scrollToSpy: ReturnType<typeof vi.fn>;
    let originalScrollTo: typeof window.scrollTo;

    beforeEach(() => {
        originalScrollTo = window.scrollTo;
        scrollToSpy = vi.fn();
        // jsdom の scrollTo を spy で置き換え
        window.scrollTo = scrollToSpy as unknown as typeof window.scrollTo;
        // requestAnimationFrame は同期実行に置き換える（テストを簡潔にするため）
        vi.spyOn(window, 'requestAnimationFrame').mockImplementation((cb) => {
            cb(0);
            return 0;
        });
    });

    afterEach(() => {
        window.scrollTo = originalScrollTo;
        vi.restoreAllMocks();
    });

    it('初回レンダーでは scrollTo が呼ばれない', () => {
        renderHook(() => useScrollMemory('key1'));
        expect(scrollToSpy).not.toHaveBeenCalled();
    });

    it('urlKey が変わると scrollTo(0, 0) が呼ばれる（記憶なしならデフォルト 0）', () => {
        const { rerender } = renderHook(({ k }: { k: string }) => useScrollMemory(k), {
            initialProps: { k: 'a' },
        });
        rerender({ k: 'b' });
        expect(scrollToSpy).toHaveBeenCalledWith(0, 0);
    });

    it('同じ urlKey で再レンダーしても scrollTo は呼ばれない', () => {
        const { rerender } = renderHook(({ k }: { k: string }) => useScrollMemory(k), {
            initialProps: { k: 'same' },
        });
        rerender({ k: 'same' });
        expect(scrollToSpy).not.toHaveBeenCalled();
    });

    it('クリック時に現在の scrollY が urlKey 別に保存され、戻ったときに復元される', () => {
        const { rerender } = renderHook(({ k }: { k: string }) => useScrollMemory(k), {
            initialProps: { k: 'pageA' },
        });

        // pageA で scrollY=300 → クリック（capture phase）で保存
        Object.defineProperty(window, 'scrollY', { value: 300, configurable: true });
        act(() => {
            document.dispatchEvent(new MouseEvent('click', { bubbles: true }));
        });

        // pageB に遷移
        rerender({ k: 'pageB' });
        // pageB では記憶なし → scrollTo(0, 0)
        expect(scrollToSpy).toHaveBeenLastCalledWith(0, 0);

        // pageA に戻る → 保存した 300 を復元
        rerender({ k: 'pageA' });
        expect(scrollToSpy).toHaveBeenLastCalledWith(0, 300);
    });

    it('アンマウントで click イベントリスナーが解除される', () => {
        const { unmount } = renderHook(() => useScrollMemory('a'));
        const removeSpy = vi.spyOn(document, 'removeEventListener');
        unmount();
        expect(removeSpy).toHaveBeenCalledWith('click', expect.any(Function), true);
    });
});
