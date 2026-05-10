/**
 * 書籍 1 冊のサムネイル + メタ情報 + 再構築ボタン。
 */
import { CheckCircle2, Circle, RefreshCw } from 'lucide-react';

import type { BookSummary } from '../../features/novel_db/types';

interface Props {
    book: BookSummary;
    onRebuild: (bookName: string) => void;
    disabled?: boolean;
}

function formatIndexedAt(isoLike: string | null): string | null {
    if (!isoLike) return null;
    // "2026-05-09 21:50:43" のような SQLite datetime をそのまま表示
    return isoLike.replace('T', ' ').slice(0, 16);
}

export default function BookCard({ book, onRebuild, disabled }: Props) {
    const indexedAt = formatIndexedAt(book.indexed_at);
    return (
        <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden bg-white dark:bg-gray-800 flex flex-col">
            {book.thumbnail_url ? (
                <img
                    src={book.thumbnail_url}
                    alt={book.name}
                    className="w-full aspect-[3/4] object-cover bg-gray-100 dark:bg-gray-900"
                    loading="lazy"
                />
            ) : (
                <div className="w-full aspect-[3/4] bg-gray-100 dark:bg-gray-900 flex items-center justify-center text-gray-400 text-sm">
                    画像なし
                </div>
            )}
            <div className="p-3 flex-1 flex flex-col gap-2">
                <h3
                    className="text-sm font-medium text-gray-900 dark:text-gray-100 line-clamp-2"
                    title={book.name}
                >
                    {book.name}
                </h3>
                {book.authors.length > 0 && (
                    <p className="text-xs text-gray-500 dark:text-gray-400 line-clamp-1">
                        {book.authors.join(' / ')}
                    </p>
                )}
                <div className="flex items-center gap-1.5 text-xs">
                    {book.is_indexed ? (
                        <>
                            <CheckCircle2 className="w-3.5 h-3.5 text-green-600 dark:text-green-400" />
                            <span className="text-gray-600 dark:text-gray-400">
                                {book.page_count} ページ
                            </span>
                            {indexedAt && (
                                <span className="text-gray-400 dark:text-gray-500 ml-auto">
                                    {indexedAt}
                                </span>
                            )}
                        </>
                    ) : (
                        <>
                            <Circle className="w-3.5 h-3.5 text-gray-400" />
                            <span className="text-gray-500 dark:text-gray-400">未構築</span>
                        </>
                    )}
                </div>
                <button
                    onClick={() => onRebuild(book.name)}
                    disabled={disabled}
                    className="mt-1 px-2.5 py-1 text-xs rounded bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-200 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-1"
                >
                    <RefreshCw className="w-3 h-3" />
                    再構築
                </button>
            </div>
        </div>
    );
}
