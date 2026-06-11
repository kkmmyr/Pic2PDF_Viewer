/**
 * 書籍 1 冊のサムネイル + メタ情報（詳細画面への導線）。
 */
import { CheckCircle2, Circle, Pencil } from 'lucide-react';

import type { BookSummary } from '@/features/novel_db/types';
import { formatSqliteUtcAsJst } from '@/utils/date';
import BookMetaList from './BookMetaList';

interface Props {
    book: BookSummary;
    onOpenDetail: (bookName: string) => void;
    onEdit: (book: BookSummary) => void;
}

export default function BookCard({ book, onOpenDetail, onEdit }: Props) {
    return (
        <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden bg-white dark:bg-gray-800 flex flex-col">
            <button
                className="w-full text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-500"
                onClick={() => onOpenDetail(book.name)}
                aria-label={`${book.name} の詳細を開く`}
            >
                {book.thumbnail_url ? (
                    <img
                        src={book.thumbnail_url}
                        alt={book.name}
                        className="w-full aspect-[3/4] object-cover bg-gray-100 dark:bg-gray-900 hover:opacity-90 transition-opacity"
                        loading="lazy"
                    />
                ) : (
                    <div className="w-full aspect-[3/4] bg-gray-100 dark:bg-gray-900 flex items-center justify-center text-gray-400 text-sm hover:bg-gray-200 dark:hover:bg-gray-800 transition-colors">
                        画像なし
                    </div>
                )}
            </button>
            <div className="p-3 flex-1 flex flex-col gap-2">
                <div className="flex items-start gap-1">
                    <h3
                        className="flex-1 text-sm font-medium text-gray-900 dark:text-gray-100 line-clamp-2"
                        title={book.name}
                    >
                        {book.name}
                    </h3>
                    <button
                        onClick={() => onEdit(book)}
                        title="メタデータを編集"
                        className="shrink-0 p-0.5 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
                    >
                        <Pencil className="w-3 h-3" />
                    </button>
                </div>
                <BookMetaList book={book} variant="card" />
                <div className="flex items-center gap-1.5 text-xs">
                    {book.is_indexed ? (
                        <>
                            <CheckCircle2 className="w-3.5 h-3.5 text-green-600 dark:text-green-400" />
                            <span className="text-gray-600 dark:text-gray-400">
                                {book.page_count} ページ
                            </span>
                            {book.indexed_at && (
                                <span className="text-gray-400 dark:text-gray-500 ml-auto">
                                    {formatSqliteUtcAsJst(book.indexed_at)}
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
            </div>
        </div>
    );
}
