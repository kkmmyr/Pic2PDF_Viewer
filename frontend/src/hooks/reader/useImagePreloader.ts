import { useEffect } from 'react';
import { buildStaticUrl } from '../../config/api';

/**
 * 画像をプリロードするカスタムフック
 * @param imageUrls 全画像のURLリスト
 * @param currentIndex 現在のページインデックス (0-based)
 * @param preloadCount 前後何ページ分をプリロードするか
 */
export function useImagePreloader(
    imageUrls: string[] | null,
    currentIndex: number,
    preloadCount: number = 2,
) {
    useEffect(() => {
        if (!imageUrls) return;

        const preloadImage = (url: string) => {
            const img = new Image();
            img.src = buildStaticUrl(url);
        };

        // Preload next pages
        for (let i = 1; i <= preloadCount; i++) {
            if (currentIndex + i < imageUrls.length) {
                preloadImage(imageUrls[currentIndex + i]);
            }
        }

        // Preload previous pages
        for (let i = 1; i <= preloadCount; i++) {
            if (currentIndex - i >= 0) {
                preloadImage(imageUrls[currentIndex - i]);
            }
        }
    }, [imageUrls, currentIndex, preloadCount]);
}
