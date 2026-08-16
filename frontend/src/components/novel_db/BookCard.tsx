/**
 * 書籍 1 冊のサムネイル + メタ情報（詳細画面への導線）。
 */
import { CheckCircle2, Circle, Pencil } from 'lucide-react';

import { BookCardShell } from '@/components/ui/book-card-shell';
import { ReadStatePill } from '@/components/ui/read-state-pill';
import type { BookSummary } from '@/features/novel_db/types';
import BookMetaList from '@/components/novel_db/BookMetaList';

interface Props {
    book: BookSummary;
    onOpenDetail: (bookName: string) => void;
    onEdit: (book: BookSummary) => void;
}

export default function BookCard({ book, onOpenDetail, onEdit }: Props) {
    return (
        <BookCardShell
            cover={
                <button
                    type="button"
                    className="relative block aspect-[3/4] w-full bg-gray-100 text-left transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-inset focus-visible:ring-accent-500 dark:bg-gray-900"
                    onClick={() => onOpenDetail(book.name)}
                    aria-label={`${book.name} の詳細を開く`}
                >
                    {book.thumbnail_url ? (
                        <img
                            src={book.thumbnail_url}
                            alt={book.name}
                            className="absolute inset-0 h-full w-full object-cover"
                            loading="lazy"
                        />
                    ) : (
                        <span className="absolute inset-0 flex items-center justify-center text-sm font-medium text-gray-600 dark:text-gray-300">
                            画像なし
                        </span>
                    )}
                </button>
            }
            title={book.name}
            authors={
                book.authors.length > 0 ? (
                    <p className="line-clamp-1 text-xs font-medium text-gray-700 dark:text-gray-300">
                        {book.authors.join(' / ')}
                    </p>
                ) : undefined
            }
            meta={<BookMetaList book={book} variant="card" />}
            summary={
                book.catalog_summary ? (
                    <div className="border-t border-gray-100 pt-1.5 dark:border-gray-700">
                        <p className="mb-0.5 text-[11px] font-semibold text-gray-600 dark:text-gray-300">
                            短い要約
                        </p>
                        <p className="line-clamp-4 text-xs leading-normal text-gray-700 dark:text-gray-300">
                            {book.catalog_summary}
                        </p>
                    </div>
                ) : undefined
            }
            footer={
                <div className="flex w-full flex-nowrap items-center gap-1.5">
                    <ReadStatePill state={book.read_state} />
                    <div className="ml-auto flex items-center gap-1">
                        <span className="inline-flex items-center gap-1 text-xs font-medium text-gray-700 dark:text-gray-300">
                            {book.is_indexed ? (
                                <CheckCircle2
                                    aria-hidden="true"
                                    className="h-4 w-4 text-green-700 dark:text-green-400"
                                />
                            ) : (
                                <Circle
                                    aria-hidden="true"
                                    className="h-4 w-4 text-gray-600 dark:text-gray-300"
                                />
                            )}
                            {book.is_indexed ? `${book.page_count ?? 0}頁` : '未構築'}
                        </span>
                        <button
                            type="button"
                            onClick={() => onEdit(book)}
                            title="メタデータを編集"
                            aria-label={`${book.name} のメタデータを編集`}
                            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-md text-gray-600 hover:bg-gray-100 hover:text-gray-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500 dark:text-gray-300 dark:hover:bg-gray-700 dark:hover:text-white"
                        >
                            <Pencil aria-hidden="true" className="h-4 w-4" />
                        </button>
                    </div>
                </div>
            }
        />
    );
}
