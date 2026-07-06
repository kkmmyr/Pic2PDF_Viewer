/**
 * 小説詳細画面（/novel/detail/:bookName）。
 *
 * 書籍ごとの情報集約ハブ：メタ / 要約 / 登場人物 / 読書会履歴を 1 画面に集約し、
 * リーダー・読書会ページへの導線を提供する。
 * 既存セクションの下に検索・会話 QA・質問＋履歴をこの本固定スコープで追加（2026-05-14）。
 */
import { useCallback, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
    BookOpen,
    ChevronLeft,
    ExternalLink,
    Loader2,
    MessageSquare,
    Pencil,
    RefreshCw,
    ScanText,
    Sparkles,
    Wand2,
} from 'lucide-react';

import {
    BookMetaEditModal,
    CharacterDetailDialog,
    CharactersPanel,
    ChatSection,
    QuestionSection,
    RebuildJobBanner,
    SearchSection,
} from '@/components/novel_db';
import BookMetaList from '@/components/novel_db/BookMetaList';
import DiscussionHistoryItemCard from '@/components/novel_db/DiscussionHistoryItem';
import type { BookDetail } from '@/features/novel_db/types';
import {
    useBookDetail,
    useNovelDbHistory,
    useNovelDbRebuildJob,
    useNovelDetailData,
} from '@/hooks/novel_db';
import { formatSqliteUtcAsJst } from '@/utils/date';

export default function NovelDetailPage() {
    const { bookName } = useParams<{ bookName: string }>();
    const navigate = useNavigate();
    const decodedName = bookName ? decodeURIComponent(bookName) : '';

    const bookScope = { type: 'book' as const, id: decodedName };

    const { detail, isLoading, error, refetch } = useBookDetail(decodedName);
    const { status: rebuildStatus, enqueue: enqueueRebuild } = useNovelDbRebuildJob(refetch);
    const {
        items: history,
        isLoading: historyLoading,
        deleteItem: deleteHistory,
        refetch: refetchHistory,
    } = useNovelDbHistory(decodedName);

    const isLocked = rebuildStatus?.is_running ?? false;

    const [charDialog, setCharDialog] = useState<{ book: string; char: string } | null>(null);
    const [editBook, setEditBook] = useState<BookDetail | null>(null);

    const { discussions, discussionsLoading, similarBooks, similarLoading } = useNovelDetailData(
        decodedName,
        detail?.is_indexed ?? false,
    );

    const handleRead = () => void navigate(`/novel/reader/${encodeURIComponent(decodedName)}`);

    const handleOpenScene = useCallback(
        (book: string, pageNo: number) =>
            void navigate(`/novel/reader/${encodeURIComponent(book)}?page=${pageNo}`),
        [navigate],
    );

    const handleOpenDiscussions = () =>
        void navigate(`/novel/discussion?book=${encodeURIComponent(decodedName)}`);

    if (isLoading) {
        return (
            <div className="flex items-center justify-center py-24">
                <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
            </div>
        );
    }

    if (error || !detail) {
        return (
            <div className="max-w-3xl mx-auto px-4 py-12 text-center text-gray-500 dark:text-gray-400">
                <p>書籍が見つかりません: {decodedName}</p>
                <button
                    onClick={() => void navigate('/novel/db')}
                    className="mt-4 text-sm text-primary-600 dark:text-primary-400 hover:underline"
                >
                    ライブラリに戻る
                </button>
            </div>
        );
    }

    return (
        <div className="max-w-3xl mx-auto px-4 py-6 space-y-6">
            {/* 戻るリンク */}
            <button
                onClick={() => void navigate('/novel/db')}
                className="flex items-center gap-1 text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
            >
                <ChevronLeft className="w-4 h-4" />
                ライブラリに戻る
            </button>

            {/* ヘッダー: サムネ + メタ + アクション */}
            <div className="flex gap-4">
                {detail.thumbnail_url && (
                    <img
                        src={detail.thumbnail_url}
                        alt={detail.name}
                        className="w-28 rounded-lg object-cover bg-gray-100 dark:bg-gray-900 shrink-0"
                    />
                )}
                <div className="flex-1 min-w-0 space-y-2">
                    <div className="flex items-start gap-2">
                        <h1 className="flex-1 text-lg font-bold text-gray-900 dark:text-gray-100 leading-snug">
                            {detail.name}
                        </h1>
                        <button
                            onClick={() => setEditBook(detail)}
                            title="メタデータを編集"
                            className="shrink-0 p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
                        >
                            <Pencil className="w-4 h-4" />
                        </button>
                    </div>

                    {/* メタ情報 */}
                    <BookMetaList book={detail} variant="detail" />

                    {/* アクションボタン */}
                    <div className="flex flex-wrap gap-2 pt-1">
                        <button
                            onClick={handleRead}
                            className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium bg-primary-600 hover:bg-primary-700 text-white rounded-lg transition-colors"
                        >
                            <BookOpen className="w-4 h-4" />
                            読む
                        </button>
                        <button
                            onClick={() =>
                                void enqueueRebuild({
                                    type: 'book',
                                    mode: 'ocr',
                                    target_id: decodedName,
                                })
                            }
                            title={
                                detail.ocr_done_at
                                    ? `OCR 済み: ${formatSqliteUtcAsJst(detail.ocr_done_at)}`
                                    : 'OCR 未実施'
                            }
                            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg transition-colors ${
                                detail.ocr_done_at
                                    ? 'bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-200'
                                    : 'bg-amber-100 dark:bg-amber-900/40 hover:bg-amber-200 dark:hover:bg-amber-800/60 text-amber-800 dark:text-amber-300'
                            }`}
                        >
                            <ScanText className="w-3.5 h-3.5" />
                            OCR
                        </button>
                        <button
                            onClick={() =>
                                void enqueueRebuild({ type: 'book', target_id: decodedName })
                            }
                            className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-200 transition-colors"
                        >
                            <RefreshCw className="w-3.5 h-3.5" />
                            再構築
                        </button>
                        {detail.ocr_done_at && (
                            <button
                                onClick={() =>
                                    void enqueueRebuild({
                                        type: 'book',
                                        mode: 'full_build',
                                        target_id: decodedName,
                                    })
                                }
                                title="チャンク再構築 → サマリ → 登場人物抽出 → キャラ辞典 → コンテキスト生成を一括実行"
                                className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg bg-indigo-100 dark:bg-indigo-900/40 hover:bg-indigo-200 dark:hover:bg-indigo-800/60 text-indigo-800 dark:text-indigo-300 transition-colors"
                            >
                                <Wand2 className="w-3.5 h-3.5" />
                                Full Build
                            </button>
                        )}
                    </div>
                </div>
            </div>

            {/* 再構築バナー */}
            <RebuildJobBanner status={rebuildStatus} />

            {/* 要約セクション */}
            <section className="space-y-2">
                <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wide">
                    あらすじ・要約
                </h2>
                {detail.summary ? (
                    <p className="text-sm text-gray-800 dark:text-gray-200 whitespace-pre-wrap leading-relaxed">
                        {detail.summary}
                    </p>
                ) : (
                    <p className="text-sm text-gray-400 dark:text-gray-500 italic">
                        要約は未生成です（Full Build を実行してください）
                    </p>
                )}
            </section>

            {/* 登場人物セクション */}
            {detail.is_indexed && (
                <section className="space-y-2">
                    <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wide">
                        登場人物{detail.character_count > 0 ? ` (${detail.character_count})` : ''}
                    </h2>
                    <CharactersPanel
                        bookName={decodedName}
                        expanded={true}
                        onSelect={(charName) =>
                            setCharDialog({ book: decodedName, char: charName })
                        }
                    />
                </section>
            )}

            {/* 似ているテーマの本セクション */}
            {detail.is_indexed && (
                <section className="space-y-2">
                    <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wide flex items-center gap-1.5">
                        <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
                        似ているテーマの本
                        {similarLoading && (
                            <Loader2 className="inline w-3.5 h-3.5 ml-1 animate-spin text-gray-400" />
                        )}
                    </h2>
                    {!similarLoading && similarBooks.length === 0 ? (
                        <p className="text-sm text-gray-400 dark:text-gray-500 italic">
                            類似書籍が見つかりません（サマリ未生成の可能性があります）
                        </p>
                    ) : (
                        <div className="flex flex-wrap gap-2">
                            {similarBooks.map((b) => (
                                <button
                                    key={b.name}
                                    onClick={() =>
                                        void navigate(`/novel/detail/${encodeURIComponent(b.name)}`)
                                    }
                                    className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg border border-indigo-200 dark:border-indigo-800 bg-indigo-50 dark:bg-indigo-900/20 text-indigo-800 dark:text-indigo-200 hover:bg-indigo-100 dark:hover:bg-indigo-900/40 transition-colors"
                                >
                                    <BookOpen className="w-3.5 h-3.5 shrink-0" />
                                    <span className="truncate max-w-48">{b.name}</span>
                                </button>
                            ))}
                        </div>
                    )}
                </section>
            )}

            {/* 読書会履歴セクション */}
            <section className="space-y-2">
                <div className="flex items-center justify-between">
                    <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wide">
                        読書会履歴
                        {detail.discussion_count > 0 ? ` (${detail.discussion_count})` : ''}
                        {discussionsLoading && (
                            <Loader2 className="inline w-3.5 h-3.5 ml-2 animate-spin text-gray-400" />
                        )}
                    </h2>
                    <button
                        onClick={handleOpenDiscussions}
                        className="flex items-center gap-1 text-xs text-primary-600 dark:text-primary-400 hover:underline"
                    >
                        <MessageSquare className="w-3.5 h-3.5" />
                        読書会ページへ
                        <ExternalLink className="w-3 h-3" />
                    </button>
                </div>
                {discussions.length === 0 && !discussionsLoading ? (
                    <p className="text-sm text-gray-400 dark:text-gray-500 italic">
                        読書会はまだ生成されていません
                    </p>
                ) : (
                    <div className="space-y-2">
                        {discussions.slice(0, 3).map((item) => (
                            <DiscussionHistoryItemCard
                                key={item.filename}
                                item={item}
                                bookName={decodedName}
                            />
                        ))}
                        {discussions.length > 3 && (
                            <button
                                onClick={handleOpenDiscussions}
                                className="text-xs text-primary-600 dark:text-primary-400 hover:underline"
                            >
                                他 {discussions.length - 3} 件を読書会ページで見る →
                            </button>
                        )}
                    </div>
                )}
            </section>

            {/* 検索・会話 QA・質問＋履歴（この本固定スコープ） */}
            <SearchSection scope={bookScope} onOpenImage={handleOpenScene} disabled={isLocked} />
            <ChatSection scope={bookScope} disabled={isLocked} />
            <QuestionSection
                scope={bookScope}
                history={history}
                historyLoading={historyLoading}
                onHistoryDelete={(id) => void deleteHistory(id)}
                onHistoryRefetch={refetchHistory}
                onOpenImage={handleOpenScene}
                disabled={isLocked}
            />

            {/* ダイアログ類 */}
            <CharacterDetailDialog
                bookName={charDialog?.book ?? null}
                charName={charDialog?.char ?? null}
                onClose={() => setCharDialog(null)}
                onOpenScene={handleOpenScene}
            />
            <BookMetaEditModal
                book={editBook}
                onClose={() => setEditBook(null)}
                onSaved={() => {
                    refetch();
                    setEditBook(null);
                }}
            />
        </div>
    );
}
