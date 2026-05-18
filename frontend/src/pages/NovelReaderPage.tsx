import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useSearchParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, BookOpen, FileText, Maximize2, Minimize2, Wand2 } from 'lucide-react';

import { useWindowSize } from '../hooks';
import { useFullscreen } from '../hooks/useFullscreen';
import { useReaderNavigation } from '../hooks/useReaderNavigation';
import { useReaderUIState } from '../hooks/useReaderUIState';
import { useSpreadMode } from '../hooks/useSpreadMode';
import { fetchBooks } from '../features/novel_db/api';
import type { SpreadMode } from '../types';

function novelImageUrl(bookName: string, pageNo: number): string {
    return `/kindle_novel/images/${encodeURIComponent(bookName)}/${String(pageNo).padStart(3, '0')}.png`;
}

async function probePageCount(bookName: string): Promise<number> {
    const first = await fetch(novelImageUrl(bookName, 1), { method: 'HEAD' });
    if (!first.ok) return 0;
    let lo = 1;
    let hi = 1500;
    while (lo < hi) {
        const mid = Math.ceil((lo + hi) / 2);
        const res = await fetch(novelImageUrl(bookName, mid), { method: 'HEAD' });
        if (res.ok) lo = mid;
        else hi = mid - 1;
    }
    return lo;
}

const SPREAD_ICON: Record<SpreadMode, React.ReactNode> = {
    auto: <Wand2 className="w-4 h-4" />,
    spread: <BookOpen className="w-4 h-4" />,
    single: <FileText className="w-4 h-4" />,
};
const SPREAD_LABEL: Record<SpreadMode, string> = { auto: 'Auto', spread: 'Spread', single: 'Single' };

const HEADER_H = 56;

export default function NovelReaderPage() {
    const { bookName } = useParams<{ bookName: string }>();
    const [searchParams] = useSearchParams();
    const navigate = useNavigate();
    const initialPage = Math.max(1, parseInt(searchParams.get('page') ?? '1', 10) || 1);

    const [numPages, setNumPages] = useState(0);
    const [direction, setDirection] = useState<'rtl' | 'ltr'>('rtl');
    const initialPageSet = useRef(false);

    const { height: windowHeight } = useWindowSize();
    const { spreadMode, isSpread, cycleSpreadMode, handlePageSize, resetAutoSpread } = useSpreadMode();
    const { isFullscreen, toggleFullscreen } = useFullscreen();
    const { showHeader, showHeaderOff, showSlider, showSliderOff } = useReaderUIState();

    const { pageNumber, setPageNumber, handleNext, handlePrev } = useReaderNavigation({
        numPages,
        isSpread,
        direction,
        isActive: numPages > 0,
    });

    useEffect(() => {
        if (!bookName) return;
        void (async () => {
            const books = await fetchBooks();
            const book = books.find((b) => b.name === bookName);
            if (book?.page_count) {
                setNumPages(book.page_count);
            } else {
                const count = await probePageCount(bookName);
                setNumPages(count);
            }
        })();
    }, [bookName]);

    useEffect(() => {
        if (numPages > 0 && initialPage > 1 && !initialPageSet.current) {
            initialPageSet.current = true;
            setPageNumber(Math.min(initialPage, numPages));
        }
    }, [numPages, initialPage, setPageNumber]);

    useEffect(() => {
        resetAutoSpread();
    }, [pageNumber, resetAutoSpread]);

    const handleClose = useCallback(() => void navigate('/novel/db'), [navigate]);
    const toggleDirection = useCallback(
        () => setDirection((d) => (d === 'rtl' ? 'ltr' : 'rtl')),
        [],
    );

    // 左半分クリック: RTL=次へ / LTR=前へ、右半分はその逆
    const handleAreaClick = useCallback(
        (e: React.MouseEvent<HTMLDivElement>) => {
            const rect = e.currentTarget.getBoundingClientRect();
            const isLeftHalf = e.clientX < rect.left + rect.width / 2;
            if (direction === 'rtl') {
                if (isLeftHalf) handleNext();
                else handlePrev();
            } else {
                if (isLeftHalf) handlePrev();
                else handleNext();
            }
        },
        [direction, handleNext, handlePrev],
    );

    if (!bookName) return null;

    const contentH = windowHeight - HEADER_H;

    // 表示するページを決定
    const showSpread = isSpread && !(direction === 'rtl' && pageNumber === 1);
    const leftPage = showSpread
        ? direction === 'rtl'
            ? pageNumber + 1 <= numPages
                ? pageNumber + 1
                : null
            : pageNumber
        : null;
    const rightPage = showSpread
        ? direction === 'rtl'
            ? pageNumber
            : pageNumber + 1 <= numPages
              ? pageNumber + 1
              : null
        : null;
    const singlePage = showSpread ? null : pageNumber;

    const imgStyle = (maxW: string) =>
        ({
            maxHeight: contentH,
            maxWidth: maxW,
            width: 'auto',
        }) as React.CSSProperties;

    return (
        <div className="fixed inset-0 bg-gray-900 z-50 flex flex-col overflow-hidden">
            {/* ヘッダー */}
            <div
                className={`fixed top-0 left-0 right-0 h-14 bg-white/95 dark:bg-gray-900/95 backdrop-blur-sm border-b border-gray-200 dark:border-gray-700 flex items-center px-4 justify-between z-50 transition-transform duration-300 ${showHeader ? 'translate-y-0' : '-translate-y-full'}`}
                onMouseLeave={showHeaderOff}
            >
                <div className="flex items-center gap-3">
                    <button
                        onClick={handleClose}
                        className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-full"
                        aria-label="ライブラリに戻る"
                    >
                        <ArrowLeft className="w-5 h-5 text-gray-700 dark:text-gray-300" />
                    </button>
                    <h1 className="font-semibold truncate max-w-md text-gray-900 dark:text-gray-100">
                        {bookName}
                    </h1>
                </div>
                <div className="flex items-center gap-2">
                    <button
                        onClick={toggleDirection}
                        className="px-3 py-1.5 text-sm bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-md transition-colors"
                    >
                        {direction === 'rtl' ? '右綴じ (RTL)' : '左綴じ (LTR)'}
                    </button>
                    <button
                        onClick={cycleSpreadMode}
                        title={`現在: ${SPREAD_LABEL[spreadMode]}`}
                        className={`px-3 py-1.5 text-sm rounded-md flex items-center gap-1.5 transition-colors ${
                            spreadMode === 'auto'
                                ? 'bg-accent-100 dark:bg-accent-900/40 text-accent-700 dark:text-accent-300'
                                : 'bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300'
                        }`}
                    >
                        {SPREAD_ICON[spreadMode]}
                        {SPREAD_LABEL[spreadMode]}
                    </button>
                    {numPages > 0 && (
                        <span className="text-sm tabular-nums text-gray-500 dark:text-gray-400">
                            {pageNumber} / {numPages}
                        </span>
                    )}
                    <button
                        onClick={() => void toggleFullscreen()}
                        className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-full"
                        aria-label={isFullscreen ? 'フルスクリーン終了' : 'フルスクリーン'}
                    >
                        {isFullscreen ? (
                            <Minimize2 className="w-4 h-4 text-gray-700 dark:text-gray-300" />
                        ) : (
                            <Maximize2 className="w-4 h-4 text-gray-700 dark:text-gray-300" />
                        )}
                    </button>
                </div>
            </div>

            {/* コンテンツ */}
            <div
                className="flex items-center justify-center cursor-pointer"
                style={{ marginTop: HEADER_H, height: contentH }}
                onClick={handleAreaClick}
            >
                {numPages === 0 ? (
                    <p className="text-gray-400">読み込み中...</p>
                ) : (
                    <div className="flex items-center">
                        {leftPage !== null && (
                            <img
                                key={`l-${leftPage}`}
                                src={novelImageUrl(bookName, leftPage)}
                                alt={`page ${leftPage}`}
                                className="object-contain bg-white"
                                style={imgStyle('50vw')}
                                onLoad={(e) => {
                                    const img = e.currentTarget;
                                    handlePageSize(img.naturalWidth, img.naturalHeight);
                                }}
                            />
                        )}
                        {rightPage !== null && (
                            <img
                                key={`r-${rightPage}`}
                                src={novelImageUrl(bookName, rightPage)}
                                alt={`page ${rightPage}`}
                                className="object-contain bg-white"
                                style={imgStyle('50vw')}
                                onLoad={(e) => {
                                    const img = e.currentTarget;
                                    handlePageSize(img.naturalWidth, img.naturalHeight);
                                }}
                            />
                        )}
                        {singlePage !== null && (
                            <img
                                key={`s-${singlePage}`}
                                src={novelImageUrl(bookName, singlePage)}
                                alt={`page ${singlePage}`}
                                className="object-contain bg-white"
                                style={imgStyle('100vw')}
                                onLoad={(e) => {
                                    const img = e.currentTarget;
                                    handlePageSize(img.naturalWidth, img.naturalHeight);
                                }}
                            />
                        )}
                    </div>
                )}
            </div>

            {/* ページスライダー */}
            {numPages > 0 && (
                <div
                    className={`fixed bottom-0 left-0 right-0 h-12 bg-white/95 dark:bg-gray-900/95 backdrop-blur-sm border-t border-gray-200 dark:border-gray-700 flex items-center px-6 gap-3 z-50 transition-transform duration-300 ${showSlider ? 'translate-y-0' : 'translate-y-full'}`}
                    onMouseLeave={showSliderOff}
                >
                    <span className="text-xs tabular-nums text-gray-500 dark:text-gray-400 w-8 text-right">
                        {pageNumber}
                    </span>
                    <input
                        type="range"
                        min={1}
                        max={numPages}
                        value={pageNumber}
                        dir={direction === 'rtl' ? 'rtl' : 'ltr'}
                        onChange={(e) => setPageNumber(Number(e.target.value))}
                        className="flex-1"
                    />
                    <span className="text-xs tabular-nums text-gray-500 dark:text-gray-400 w-8">
                        {numPages}
                    </span>
                </div>
            )}

        </div>
    );
}
