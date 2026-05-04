import { useEffect, useRef } from 'react';

/**
 * URL 状態（キー文字列）ごとにスクロール位置を保存し、戻ってきた時に復元する。
 *
 * - クリックの capture phase で navigate 前に現在位置を保存する
 *   （SPA で navigate 後だと既に新しい URL キーになっており、保存先を間違える）
 * - URL キーが変わったら保存済み位置に `requestAnimationFrame` 経由で復元する
 *   （display 切替・コンテンツ変更後の reflow を待つため）
 * - 初回レンダーは復元しない（ブラウザのスクロール復元と競合させない）
 */
export function useScrollMemory(urlKey: string) {
    const scrollMemory = useRef(new Map<string, number>());

    // 現在の urlKey を ref で参照（capture handler が古いキーで保存しないように）
    const currentUrlKeyRef = useRef(urlKey);
    currentUrlKeyRef.current = urlKey;

    useEffect(() => {
        const onClickCapture = () => {
            scrollMemory.current.set(currentUrlKeyRef.current, window.scrollY);
        };
        document.addEventListener('click', onClickCapture, true);
        return () => document.removeEventListener('click', onClickCapture, true);
    }, []);

    const isFirstRenderRef = useRef(true);
    useEffect(() => {
        if (isFirstRenderRef.current) {
            isFirstRenderRef.current = false;
            return;
        }
        const targetY = scrollMemory.current.get(urlKey) ?? 0;
        requestAnimationFrame(() => {
            window.scrollTo(0, targetY);
        });
    }, [urlKey]);
}
