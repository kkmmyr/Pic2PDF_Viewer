/**
 * 小説テキスト検索・RAG 機能のトップページ。
 *
 * 1 タブ内に「ライブラリ / 検索 / 質問」を縦並び配置し、
 * ヘッダーのスコープドロップダウンで対象を全件 / シリーズ / 単冊から選択する。
 */
import { useState } from 'react';

import {
    CharacterDetailDialog,
    ChatSection,
    LibrarySection,
    NovelDbHeader,
    PageImageModal,
    QuestionSection,
    RebuildJobBanner,
    SearchSection,
} from '../components/novel_db';
import {
    useNovelDbBooks,
    useNovelDbHistory,
    useNovelDbPageImageModal,
    useNovelDbRebuildJob,
    useNovelDbScope,
} from '../hooks/novel_db';

export default function NovelDbPage() {
    const { scope, setScope } = useNovelDbScope();
    const { books, series, isLoading: booksLoading, refetch: refetchBooks } = useNovelDbBooks();
    const {
        items: history,
        isLoading: historyLoading,
        deleteItem: deleteHistory,
        refetch: refetchHistory,
    } = useNovelDbHistory();
    const { status: rebuildStatus, enqueue: enqueueRebuild } = useNovelDbRebuildJob(() => {
        // ジョブ完了通知 → 書籍一覧を再取得
        void refetchBooks();
    });
    const imageModal = useNovelDbPageImageModal(books);

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
                onSelectCharacter={handleSelectCharacter}
                rebuildStatus={rebuildStatus}
            />
            <SearchSection scope={scope} onOpenImage={imageModal.open} disabled={isLocked} />
            <QuestionSection
                scope={scope}
                history={history}
                historyLoading={historyLoading}
                onHistoryDelete={(id) => void deleteHistory(id)}
                onHistoryRefetch={refetchHistory}
                onOpenImage={imageModal.open}
                disabled={isLocked}
            />
            <ChatSection scope={scope} disabled={isLocked} />
            {imageModal.state && (
                <PageImageModal
                    book={imageModal.state.book}
                    pageNo={imageModal.state.pageNo}
                    maxPage={imageModal.maxPage}
                    onClose={imageModal.close}
                    onPrev={imageModal.prevPage}
                    onNext={imageModal.nextPage}
                />
            )}
            <CharacterDetailDialog
                bookName={charDialog?.book ?? null}
                charName={charDialog?.char ?? null}
                onClose={() => setCharDialog(null)}
                onOpenScene={(book, pageNo) => imageModal.open(book, pageNo)}
            />
        </div>
    );
}
