import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';

import { BookMetaEditModal, LibrarySection, SearchSection } from '../components/novel_db';
import type { BookSummary } from '../features/novel_db/types';
import { useNovelDbBooks } from '../hooks/novel_db';

export default function NovelDbPage() {
    const navigate = useNavigate();
    const { books, isLoading: booksLoading, refetch: refetchBooks } = useNovelDbBooks();

    const [editBook, setEditBook] = useState<BookSummary | null>(null);

    const handleOpenDetail = useCallback(
        (bookName: string) => {
            void navigate(`/novel/detail/${encodeURIComponent(bookName)}`);
        },
        [navigate],
    );

    const handleOpenImage = useCallback(
        (book: string, pageNo: number) => {
            void navigate(`/novel/reader/${encodeURIComponent(book)}?page=${pageNo}`);
        },
        [navigate],
    );

    return (
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
            <LibrarySection
                books={books}
                isLoading={booksLoading}
                onOpenDetailBook={handleOpenDetail}
                onEditBook={setEditBook}
                onMetaRefetch={() => void refetchBooks()}
            />
            <BookMetaEditModal
                book={editBook}
                onClose={() => setEditBook(null)}
                onSaved={() => void refetchBooks()}
            />
            <SearchSection scope={{ type: 'all' }} onOpenImage={handleOpenImage} />
        </div>
    );
}
