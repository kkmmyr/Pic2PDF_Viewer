/**
 * 検索結果 / 質問の引用ページ画像モーダル。
 * 左右キー / ボタンで前後ページ送り、× / ESC / 背景クリックで閉じる。
 */
import { ChevronLeft, ChevronRight, X } from 'lucide-react';

interface Props {
    book: string;
    pageNo: number;
    maxPage: number;
    onClose: () => void;
    onPrev: () => void;
    onNext: () => void;
}

function imageUrl(book: string, pageNo: number): string {
    return `/kindle_novel/images/${encodeURIComponent(book)}/${String(pageNo).padStart(3, '0')}.png`;
}

export default function PageImageModal({ book, pageNo, maxPage, onClose, onPrev, onNext }: Props) {
    return (
        <div className="fixed inset-0 z-dialog flex items-center justify-center p-4">
            <button
                type="button"
                className="absolute inset-0 bg-black/70 cursor-default"
                onClick={onClose}
                aria-label="背景を選択して閉じる"
            />
            <div
                className="relative max-w-screen-lg max-h-full w-full flex flex-col items-center"
                role="dialog"
                aria-modal="true"
                aria-label={`${book} ページ ${pageNo}`}
            >
                <div className="w-full flex items-center justify-between text-white text-sm mb-2 px-2">
                    <div className="truncate">
                        {book}
                        <span className="opacity-70 ml-2">page {pageNo}</span>
                    </div>
                    <button
                        type="button"
                        onClick={onClose}
                        className="p-1.5 rounded hover:bg-white/10"
                        aria-label="閉じる"
                    >
                        <X className="w-5 h-5" />
                    </button>
                </div>
                <div className="relative flex items-center justify-center w-full">
                    <button
                        type="button"
                        onClick={onPrev}
                        disabled={pageNo <= 1}
                        className="absolute left-0 p-2 rounded-full bg-white/10 hover:bg-white/20 text-white disabled:opacity-30 disabled:cursor-not-allowed"
                        aria-label="前のページ"
                    >
                        <ChevronLeft className="w-6 h-6" />
                    </button>
                    <img
                        key={`${book}-${pageNo}`}
                        src={imageUrl(book, pageNo)}
                        alt={`${book} page ${pageNo}`}
                        className="max-h-[85vh] max-w-full object-contain"
                    />
                    <button
                        type="button"
                        onClick={onNext}
                        disabled={maxPage > 0 && pageNo >= maxPage}
                        className="absolute right-0 p-2 rounded-full bg-white/10 hover:bg-white/20 text-white disabled:opacity-30 disabled:cursor-not-allowed"
                        aria-label="次のページ"
                    >
                        <ChevronRight className="w-6 h-6" />
                    </button>
                </div>
            </div>
        </div>
    );
}
