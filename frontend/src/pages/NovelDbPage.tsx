/**
 * 小説テキスト検索・RAG 機能のトップページ。
 *
 * 1 タブ内に「ライブラリ / 検索 / 質問」を縦並び配置し、
 * ヘッダーのスコープドロップダウンで対象を全件 / シリーズ / 単冊から選択する。
 */
import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';

import {
    BookMetaEditModal,
    ChatSection,
    LibrarySection,
    NovelDbHeader,
    QuestionSection,
    RebuildJobBanner,
    SearchSection,
} from '../components/novel_db';
import type { BookSummary } from '../features/novel_db/types';
import {
    useNovelDbBooks,
    useNovelDbHistory,
    useNovelDbRebuildJob,
    useNovelDbScope,
} from '../hooks/novel_db';

export default function NovelDbPage() {
    const navigate = useNavigate();
    const { scope, setScope } = useNovelDbScope();
    const { books, series, isLoading: booksLoading, refetch: refetchBooks } = useNovelDbBooks();
    const {
        items: history,
        isLoading: historyLoading,
        deleteItem: deleteHistory,
        refetch: refetchHistory,
    } = useNovelDbHistory();
    const { status: rebuildStatus, enqueue: enqueueRebuild } = useNovelDbRebuildJob(() => {
        void refetchBooks();
    });

    const [editBook, setEditBook] = useState<BookSummary | null>(null);

    const isLocked = rebuildStatus?.is_running ?? false;

    const handleRebuildAll = () => {
        void enqueueRebuild({ type: 'all' });
    };

    // 書籍カードクリック → 詳細画面へ
    const handleOpenDetail = useCallback(
        (bookName: string) => {
            void navigate(`/novel/detail/${encodeURIComponent(bookName)}`);
        },
        [navigate],
    );

    // 検索/AI 結果のページ番号からリーダーへジャンプ
    const handleOpenImage = useCallback(
        (book: string, pageNo: number) => {
            void navigate(`/novel/reader/${encodeURIComponent(book)}?page=${pageNo}`);
        },
        [navigate],
    );

    return (
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
            <NovelDbHeader
                scope={scope}
                onScopeChange={setScope}
                books={books}
                series={series}
                onRebuildAll={handleRebuildAll}
                rebuildStatus={rebuildStatus}
            />
            <RebuildJobBanner status={rebuildStatus} />
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
            <SearchSection scope={scope} onOpenImage={handleOpenImage} disabled={isLocked} />
            <QuestionSection
                scope={scope}
                history={history}
                historyLoading={historyLoading}
                onHistoryDelete={(id) => void deleteHistory(id)}
                onHistoryRefetch={refetchHistory}
                onOpenImage={handleOpenImage}
                disabled={isLocked}
            />
            <ChatSection scope={scope} disabled={isLocked} />
        </div>
    );
}
