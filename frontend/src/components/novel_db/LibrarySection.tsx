/**
 * ライブラリ（書籍一覧）セクション。
 */
import type { BookSummary } from '../../features/novel_db/types';

import AmazonCsvImportSection from './AmazonCsvImportSection';
import BookCard from './BookCard';

interface Props {
    books: BookSummary[];
    isLoading: boolean;
    onOpenDetailBook: (bookName: string) => void;
    onEditBook: (book: BookSummary) => void;
    onMetaRefetch: () => void;
}

export default function LibrarySection({
    books,
    isLoading,
    onOpenDetailBook,
    onEditBook,
    onMetaRefetch,
}: Props) {
    return (
        <section className="space-y-3">
            <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                    ライブラリ ({books.length} 冊)
                </h2>
                <AmazonCsvImportSection books={books} onApplied={onMetaRefetch} />
            </div>
            {isLoading && books.length === 0 ? (
                <p className="text-sm text-gray-500">読み込み中...</p>
            ) : books.length === 0 ? (
                <p className="text-sm text-gray-500">novel ソースに書籍が見つかりません。</p>
            ) : (
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3">
                    {books.map((b) => (
                        <BookCard
                            key={b.name}
                            book={b}
                            onOpenDetail={onOpenDetailBook}
                            onEdit={onEditBook}
                        />
                    ))}
                </div>
            )}
        </section>
    );
}
