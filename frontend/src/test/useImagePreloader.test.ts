import { renderHook } from '@testing-library/react';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { useImagePreloader } from '../hooks/reader/useImagePreloader';

describe('useImagePreloader', () => {
    let originalImage: typeof window.Image;
    let createdImages: { src: string }[];

    beforeEach(() => {
        createdImages = [];
        originalImage = window.Image;
        // new Image() を捕捉。src setter で URL を記録
        window.Image = class FakeImage {
            private _src = '';
            get src() {
                return this._src;
            }
            set src(v: string) {
                this._src = v;
                createdImages.push({ src: v });
            }
        } as unknown as typeof window.Image;
    });

    afterEach(() => {
        window.Image = originalImage;
    });

    it('imageUrls=null では何も preload しない', () => {
        renderHook(() => useImagePreloader(null, 0));
        expect(createdImages).toHaveLength(0);
    });

    it('既定 preloadCount=2 で前後 2 ページ分の画像を preload する', () => {
        const urls = ['/a.webp', '/b.webp', '/c.webp', '/d.webp', '/e.webp'];
        renderHook(() => useImagePreloader(urls, 2));
        // 前後 2 → c=2 を中心に [d, e]（次）+ [b, a]（前）= 4 件
        expect(createdImages).toHaveLength(4);
    });

    it('範囲外（先頭）の前ページは preload しない', () => {
        const urls = ['/a.webp', '/b.webp', '/c.webp'];
        renderHook(() => useImagePreloader(urls, 0));
        // currentIndex=0 → 次 2 件のみ
        expect(createdImages).toHaveLength(2);
    });

    it('範囲外（末尾）の次ページは preload しない', () => {
        const urls = ['/a.webp', '/b.webp', '/c.webp'];
        renderHook(() => useImagePreloader(urls, 2));
        // currentIndex=2 → 前 2 件のみ
        expect(createdImages).toHaveLength(2);
    });

    it('preloadCount を変更できる（=1 で前後 1 ページのみ）', () => {
        const urls = ['/a.webp', '/b.webp', '/c.webp', '/d.webp', '/e.webp'];
        renderHook(() => useImagePreloader(urls, 2, 1));
        expect(createdImages).toHaveLength(2);
    });

    it('現在ページの画像は preload しない', () => {
        const urls = ['/a.webp', '/b.webp', '/c.webp'];
        renderHook(() => useImagePreloader(urls, 1, 0));
        // preloadCount=0 で前後 0 件 → 何もしない
        expect(createdImages).toHaveLength(0);
    });
});
