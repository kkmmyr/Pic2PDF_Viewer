/**
 * ライブラリ（書籍一覧）セクション。
 */
import type { BookSummary, RebuildStatus } from '../../features/novel_db/types';

import BookCard from './BookCard';

interface Props {
    books: BookSummary[];
    isLoading: boolean;
    onRebuildBook: (bookName: string) => void;
    onReadBook: (bookName: string) => void;
    /** B-15: 登場人物セクションでキャラ選択時に親が CharacterDetailDialog を開く。 */
    onSelectCharacter?: (bookName: string, charName: string) => void;
    rebuildStatus: RebuildStatus | null;
}

export default function LibrarySection({
    books,
    isLoading,
    onRebuildBook,
    onReadBook,
    onSelectCharacter,
    rebuildStatus,
}: Props) {
    const isLocked = rebuildStatus?.is_running ?? false;
    return (
        <section className="space-y-3">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                ライブラリ ({books.length} 冊)
            </h2>
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
                            onRebuild={onRebuildBook}
                            onRead={onReadBook}
                            onSelectCharacter={onSelectCharacter}
                            disabled={isLocked}
                        />
                    ))}
                </div>
            )}
        </section>
    );
}
