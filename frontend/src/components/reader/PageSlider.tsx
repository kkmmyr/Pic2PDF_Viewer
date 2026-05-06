import { useState, useCallback, useEffect, useRef } from 'react';
import type { ReadingDirection, LibrarySource } from '../../types';
import { API_ENDPOINTS, buildApiUrl } from '../../config/api';

interface PageSliderProps {
    pageNumber: number;
    numPages: number;
    isSpread: boolean;
    direction: ReadingDirection;
    show: boolean;
    selectedPdf: string;
    currentPath: string;
    currentSource: LibrarySource;
    onPageJump: (page: number) => void;
    onMouseLeave?: () => void;
}

/**
 * RTL/LTR 見開きモードにおいて、スライダーでジャンプした先のページを
 * 左ページ境界（有効な開始ページ）に正規化する。
 *
 * - RTL spread: 有効開始ページは 1, 2, 4, 6, … (1 は単独表紙、以降は偶数)
 * - LTR spread: 有効開始ページは 1, 3, 5, … (奇数)
 */
function normalizeSpreadPage(page: number, isSpread: boolean, direction: ReadingDirection): number {
    if (!isSpread) return page;
    if (direction === 'rtl') {
        if (page === 1) return 1;
        return page % 2 === 0 ? page : page - 1;
    }
    return page % 2 === 1 ? page : Math.max(1, page - 1);
}

/**
 * リーダー画面下部に表示するページスライダーバー。
 *
 * - ドラッグ中は pendingPage をローカルで管理し、離した瞬間だけ onPageJump を呼ぶ
 *   （react-pdf の描画コストを毎 tick 発生させないため）
 * - ドラッグ中は 150ms デバウンスで GET /api/thumbnails/page を呼び、サムネイルを表示
 * - RTL モード: slider を scaleX(-1) でビジュアルだけ反転（値は LTR のまま）
 * - tabIndex={-1} + onFocus blur: 矢印キーを useReaderNavigation に完全委譲
 */
export function PageSlider({
    pageNumber,
    numPages,
    isSpread,
    direction,
    show,
    selectedPdf,
    currentPath,
    currentSource,
    onPageJump,
    onMouseLeave,
}: PageSliderProps) {
    const [isDragging, setIsDragging] = useState(false);
    const [pendingPage, setPendingPage] = useState(1);
    const [thumbPage, setThumbPage] = useState(1);
    const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    const displayPage = isDragging ? pendingPage : pageNumber;

    // pendingPage が変わるたびに 150ms デバウンスでサムネイルページを更新
    useEffect(() => {
        if (!isDragging) return;
        if (debounceRef.current) clearTimeout(debounceRef.current);
        debounceRef.current = setTimeout(() => setThumbPage(pendingPage), 150);
    }, [isDragging, pendingPage]);

    const commitPage = useCallback(
        (value: number) => {
            setIsDragging(false);
            if (debounceRef.current) clearTimeout(debounceRef.current);
            const clamped = Math.max(1, Math.min(value, numPages));
            onPageJump(normalizeSpreadPage(clamped, isSpread, direction));
        },
        [numPages, isSpread, direction, onPageJump],
    );

    if (numPages === 0) return null;

    const thumbRatio = numPages > 1 ? (displayPage - 1) / (numPages - 1) : 0;
    const tooltipLeft = direction === 'rtl' ? 1 - thumbRatio : thumbRatio;
    const thumbUrl = buildApiUrl(
        API_ENDPOINTS.PAGE_THUMBNAIL(selectedPdf, thumbPage, currentPath, currentSource),
    );

    return (
        <div
            className={`fixed bottom-0 left-0 right-0 h-12 z-overlay-bar transition-transform duration-300 ${
                !show ? 'translate-y-full' : 'translate-y-0'
            } bg-white/90 dark:bg-gray-900/90 backdrop-blur-sm border-t border-gray-200 dark:border-gray-700 flex items-center px-6 gap-3`}
            onMouseLeave={onMouseLeave}
        >
            <span className="text-xs tabular-nums text-gray-500 dark:text-gray-400 shrink-0 w-14 text-right">
                P.{displayPage}
            </span>
            <div className="relative flex-1">
                {isDragging && (
                    <div
                        className="absolute bottom-full mb-2 flex flex-col items-center pointer-events-none"
                        style={{
                            left: `clamp(0px, calc(${tooltipLeft * 100}% - 200px), calc(100% - 400px))`,
                        }}
                    >
                        <div className="bg-gray-900/90 dark:bg-gray-700/90 rounded shadow-lg overflow-hidden">
                            <img
                                src={thumbUrl}
                                alt=""
                                width={400}
                                className="w-[400px] h-auto block"
                                onError={(e) => {
                                    (e.target as HTMLImageElement).style.display = 'none';
                                }}
                            />
                            <p className="text-white text-xs text-center tabular-nums px-1.5 py-0.5">
                                P. {pendingPage}
                            </p>
                        </div>
                    </div>
                )}
                <input
                    type="range"
                    tabIndex={-1}
                    min={1}
                    max={numPages}
                    value={displayPage}
                    onChange={(e) => {
                        setIsDragging(true);
                        setPendingPage(Number(e.target.value));
                    }}
                    onPointerUp={(e) => commitPage(Number((e.target as HTMLInputElement).value))}
                    onFocus={(e) => e.target.blur()}
                    className="w-full cursor-pointer accent-primary-600"
                    style={direction === 'rtl' ? { transform: 'scaleX(-1)' } : undefined}
                />
            </div>
            <span className="text-xs tabular-nums text-gray-500 dark:text-gray-400 shrink-0 w-14">
                / {numPages}
            </span>
        </div>
    );
}
