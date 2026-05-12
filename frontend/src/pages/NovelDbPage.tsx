/**
 * 小説テキスト検索・RAG 機能のトップページ。
 *
 * 1 タブ内に「ライブラリ / 検索 / 質問」を縦並び配置し、
 * ヘッダーのスコープドロップダウンで対象を全件 / シリーズ / 単冊から選択する。
 */
import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';

import {
    CharacterDetailDialog,
    ChatSection,
    LibrarySection,
    NovelDbHeader,
    QuestionSection,
    RebuildJobBanner,
    SearchSection,
} from '../components/novel_db';
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

    // B-15: キャラ詳細ダイアログの開閉状態
    const [charDialog, setCharDialog] = useState<{ book: string; char: string } | null>(null);

    const isLocked = rebuildStatus?.is_running ?? false;

    const handleRebuildAll = () => {
        void enqueueRebuild({ type: 'all' });
    };

    const handleRebuildBook = (bookName: string) => {
        void enqueueRebuild({ type: 'book', target_id: bookName });
    };

    const handleSelectCharacter = (bookName: string, charName: string) => {
        setCharDialog({ book: bookName, char: charName });
    };

    // 書籍を読む（表紙クリック）
    const handleReadBook = useCallback(
        (bookName: string) => {
            void navigate(`/novel/reader/${encodeURIComponent(bookName)}`);
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
                onRebuildBook={handleRebuildBook}
                onReadBook={handleReadBook}
                onSelectCharacter={handleSelectCharacter}
                rebuildStatus={rebuildStatus}
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
            <CharacterDetailDialog
                bookName={charDialog?.book ?? null}
                charName={charDialog?.char ?? null}
                onClose={() => setCharDialog(null)}
                onOpenScene={handleOpenImage}
            />
        </div>
    );
}
