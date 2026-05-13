/**
 * ライブラリ（書籍一覧）セクション。
 *
 * - トップ階層: シリーズ/作者グループカードグリッド + 未設定書籍フラット表示
 * - ドリルダウン: シリーズ内 DnD 並び替え（ドロップ時即時保存）
 * - 選択モード: フラット/グループ/ドリルダウン全モードで利用可（一括作者設定 / 一括シリーズ登録）
 */
import { useState, useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
    Check,
    Users,
    BookOpen,
    LayoutGrid,
    CheckSquare,
    Square,
    ChevronRight,
} from 'lucide-react';

import type { BookSummary, SeriesSummary } from '../../features/novel_db/types';
import { fetchNovelAuthors, fetchSeries, patchNovelBookMeta } from '../../features/novel_db/api';
import {
    type GroupMode,
    type NovelBookGroup,
    useNovelLibraryGroup,
} from '../../hooks/useNovelLibraryGroup';
import BookCard from './BookCard';
import { NovelBulkAuthorDialog } from './NovelBulkAuthorDialog';
import { NovelBulkSeriesAssignDialog } from './NovelBulkSeriesAssignDialog';
import SeriesGroupCard from './SeriesGroupCard';
import SeriesDrilldownView from './SeriesDrilldownView';

interface Props {
    books: BookSummary[];
    isLoading: boolean;
    onOpenDetailBook: (bookName: string) => void;
    onEditBook: (book: BookSummary) => void;
    onMetaRefetch: () => void;
}

const GROUP_MODES: { value: GroupMode; label: string; icon: React.ReactNode }[] = [
    { value: 'flat', label: 'フラット', icon: <LayoutGrid className="w-3.5 h-3.5" /> },
    { value: 'author', label: '作者別', icon: <Users className="w-3.5 h-3.5" /> },
    { value: 'series', label: 'シリーズ別', icon: <BookOpen className="w-3.5 h-3.5" /> },
];

export default function LibrarySection({
    books,
    isLoading,
    onOpenDetailBook,
    onEditBook,
    onMetaRefetch,
}: Props) {
    const [searchParams, setSearchParams] = useSearchParams();
    const [groupMode, setGroupMode] = useState<GroupMode>('series');
    const [isSelecting, setIsSelecting] = useState(false);
    const [selectedNames, setSelectedNames] = useState<Set<string>>(new Set());

    // ダイアログ状態
    const [showAuthorDialog, setShowAuthorDialog] = useState(false);
    const [showSeriesDialog, setShowSeriesDialog] = useState(false);
    const [allAuthors, setAllAuthors] = useState<string[]>([]);
    const [allSeriesForDialog, setAllSeriesForDialog] = useState<SeriesSummary[]>([]);

    const { groups, ungrouped } = useNovelLibraryGroup(books, groupMode);

    // URL param ?dd=<seriesId> でドリルダウン状態を管理（ブラウザバック対応）
    const drilldownId = searchParams.get('dd');
    const drilldown = useMemo(() => {
        if (!drilldownId) return null;
        const group = groups.find((g) => g.series_id === drilldownId);
        if (!group) return null;
        return { seriesId: group.series_id!, label: group.label, books: group.books };
    }, [drilldownId, groups]);

    // ---- 選択操作 ----
    const toggleSelect = useCallback((name: string) => {
        setSelectedNames((prev) => {
            const next = new Set(prev);
            if (next.has(name)) next.delete(name);
            else next.add(name);
            return next;
        });
    }, []);

    const toggleSelectAll = useCallback((targetBooks: BookSummary[]) => {
        setSelectedNames((prev) => {
            const allSelected = targetBooks.every((b) => prev.has(b.name));
            const next = new Set(prev);
            if (allSelected) {
                targetBooks.forEach((b) => next.delete(b.name));
            } else {
                targetBooks.forEach((b) => next.add(b.name));
            }
            return next;
        });
    }, []);

    const toggleGroupSelect = useCallback((group: NovelBookGroup) => {
        setSelectedNames((prev) => {
            const allSelected = group.books.every((b) => prev.has(b.name));
            const next = new Set(prev);
            if (allSelected) {
                group.books.forEach((b) => next.delete(b.name));
            } else {
                group.books.forEach((b) => next.add(b.name));
            }
            return next;
        });
    }, []);

    const exitSelecting = useCallback(() => {
        setIsSelecting(false);
        setSelectedNames(new Set());
    }, []);

    // ---- ダイアログ起動 ----
    const openAuthorDialog = async () => {
        const authors = await fetchNovelAuthors().catch(() => []);
        setAllAuthors(authors);
        setShowAuthorDialog(true);
    };

    const openSeriesDialog = async () => {
        const series = await fetchSeries().catch(() => []);
        setAllSeriesForDialog(series);
        setShowSeriesDialog(true);
    };

    // ---- 一括作者設定 ----
    const handleApplyAuthors = async (authors: string[]) => {
        const targets = books.filter((b) => selectedNames.has(b.name));
        for (const book of targets) {
            await patchNovelBookMeta(`${book.name}.pdf`, { authors });
        }
        onMetaRefetch();
        exitSelecting();
    };

    // ---- 一括シリーズ登録 ----
    const handleAssignSeries = async (params: {
        mode: 'existing' | 'new' | 'remove';
        seriesId?: string;
        seriesTitle?: string;
        volumes?: number[];
    }) => {
        const targets = books.filter((b) => selectedNames.has(b.name));
        for (let i = 0; i < targets.length; i++) {
            const book = targets[i];
            if (params.mode === 'remove') {
                await patchNovelBookMeta(`${book.name}.pdf`, { series_id: '' });
            } else {
                await patchNovelBookMeta(`${book.name}.pdf`, {
                    series_id: params.seriesId,
                    volume: params.volumes?.[i] ?? null,
                });
            }
        }
        onMetaRefetch();
        exitSelecting();
    };

    // ---- 書籍カード（選択オーバーレイ付き） ----
    const renderCard = (book: BookSummary) => {
        const selected = selectedNames.has(book.name);
        return (
            <div key={book.name} className="relative">
                <div className={selected ? 'ring-2 ring-primary-500 rounded-lg' : undefined}>
                    <BookCard
                        book={book}
                        onOpenDetail={isSelecting ? () => {} : onOpenDetailBook}
                        onEdit={onEditBook}
                    />
                </div>
                {isSelecting && (
                    <button
                        className="absolute inset-0 z-10 rounded-lg"
                        onClick={() => toggleSelect(book.name)}
                        aria-label={selected ? `${book.name} の選択を解除` : `${book.name} を選択`}
                    >
                        <span
                            className={`absolute top-1.5 left-1.5 flex items-center justify-center w-5 h-5 rounded-full border-2 ${
                                selected
                                    ? 'bg-primary-600 border-primary-600'
                                    : 'bg-white/90 dark:bg-gray-900/90 border-gray-300 dark:border-gray-600'
                            }`}
                        >
                            {selected && <Check className="w-3 h-3 text-white" />}
                        </span>
                    </button>
                )}
            </div>
        );
    };

    const selectedList = books.filter((b) => selectedNames.has(b.name));

    // ---- グループカードクリック → URL に push してドリルダウン ----
    const handleGroupClick = useCallback(
        (seriesId: string) => {
            setSearchParams(
                (prev) => {
                    const sp = new URLSearchParams(prev);
                    sp.set('dd', seriesId);
                    return sp;
                },
                { replace: false },
            );
            exitSelecting();
        },
        [setSearchParams, exitSelecting],
    );

    // ---- ドリルダウンから戻る ----
    const handleBackToLibrary = useCallback(() => {
        setSearchParams(
            (prev) => {
                const sp = new URLSearchParams(prev);
                sp.delete('dd');
                return sp;
            },
            { replace: true },
        );
        exitSelecting();
    }, [setSearchParams, exitSelecting]);

    // ---- 選択トグルボタン（共通） ----
    const renderSelectButton = () => (
        <button
            onClick={() => (isSelecting ? exitSelecting() : setIsSelecting(true))}
            className={`flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-lg border transition-colors ${
                isSelecting
                    ? 'bg-primary-100 dark:bg-primary-900/40 border-primary-400 text-primary-700 dark:text-primary-300'
                    : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
            }`}
        >
            {isSelecting ? (
                <CheckSquare className="w-3.5 h-3.5" />
            ) : (
                <Square className="w-3.5 h-3.5" />
            )}
            選択
        </button>
    );

    // ---- 選択アクションバー（共通） ----
    const renderActionBar = (targetBooks: BookSummary[]) => {
        const allSelected =
            targetBooks.length > 0 && targetBooks.every((b) => selectedNames.has(b.name));
        const selectedCount = targetBooks.filter((b) => selectedNames.has(b.name)).length;
        return (
            <div className="flex flex-wrap items-center gap-2 px-3 py-2 bg-primary-50 dark:bg-primary-900/20 border border-primary-200 dark:border-primary-800 rounded-lg text-sm">
                <button
                    onClick={() => toggleSelectAll(targetBooks)}
                    className="text-primary-600 dark:text-primary-400 underline text-xs"
                >
                    {allSelected ? '全解除' : '全選択'}
                </button>
                <span className="text-gray-600 dark:text-gray-400 text-xs">
                    {selectedCount} 冊選択中
                </span>
                <div className="flex gap-2 ml-auto">
                    <button
                        disabled={selectedNames.size === 0}
                        onClick={() => void openAuthorDialog()}
                        className="px-3 py-1 text-xs bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg disabled:opacity-40 hover:bg-gray-50 dark:hover:bg-gray-700"
                    >
                        作者を設定
                    </button>
                    <button
                        disabled={selectedNames.size === 0}
                        onClick={() => void openSeriesDialog()}
                        className="px-3 py-1 text-xs bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg disabled:opacity-40 hover:bg-gray-50 dark:hover:bg-gray-700"
                    >
                        シリーズに登録
                    </button>
                </div>
            </div>
        );
    };

    return (
        <section className="space-y-3">
            {drilldown ? (
                /* ---- ドリルダウンビュー ---- */
                <>
                    {/* パンくず + 選択ボタン */}
                    <div className="flex items-center gap-2">
                        <nav className="flex items-center gap-1 text-sm flex-1 min-w-0">
                            <button
                                onClick={handleBackToLibrary}
                                className="text-primary-600 dark:text-primary-400 hover:underline font-medium shrink-0"
                            >
                                ライブラリ
                            </button>
                            <ChevronRight className="w-4 h-4 text-gray-400 shrink-0" />
                            <span className="text-gray-900 dark:text-gray-100 font-medium truncate">
                                {drilldown.label}
                            </span>
                            <span className="text-gray-400 dark:text-gray-500 text-xs ml-1 shrink-0">
                                ({drilldown.books.length} 冊)
                            </span>
                        </nav>
                        {renderSelectButton()}
                    </div>

                    {/* 選択アクションバー */}
                    {isSelecting && renderActionBar(drilldown.books)}

                    {/* コンテンツ: 選択モードなら個別カード、通常は DnD ビュー */}
                    {isSelecting ? (
                        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3">
                            {drilldown.books.map(renderCard)}
                        </div>
                    ) : (
                        <SeriesDrilldownView
                            seriesId={drilldown.seriesId}
                            books={drilldown.books}
                            onOpenDetailBook={onOpenDetailBook}
                            onEditBook={onEditBook}
                            onReordered={onMetaRefetch}
                        />
                    )}
                </>
            ) : (
                /* ---- トップ階層ビュー ---- */
                <>
                    {/* ヘッダー */}
                    <div className="flex flex-wrap items-center gap-2">
                        <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mr-2">
                            ライブラリ ({books.length} 冊)
                        </h2>

                        {/* グループモード切替 */}
                        <div className="flex rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden text-xs">
                            {GROUP_MODES.map(({ value, label, icon }) => (
                                <button
                                    key={value}
                                    onClick={() => setGroupMode(value)}
                                    className={`flex items-center gap-1 px-2.5 py-1.5 transition-colors ${
                                        groupMode === value
                                            ? 'bg-primary-600 text-white'
                                            : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
                                    }`}
                                >
                                    {icon}
                                    {label}
                                </button>
                            ))}
                        </div>

                        {renderSelectButton()}
                    </div>

                    {/* 選択アクションバー */}
                    {isSelecting && renderActionBar(books)}

                    {/* 書籍一覧 */}
                    {isLoading && books.length === 0 ? (
                        <p className="text-sm text-gray-500">読み込み中...</p>
                    ) : books.length === 0 ? (
                        <p className="text-sm text-gray-500">
                            novel ソースに書籍が見つかりません。
                        </p>
                    ) : groupMode === 'flat' ? (
                        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3">
                            {books.map(renderCard)}
                        </div>
                    ) : (
                        <div className="space-y-6">
                            {/* グループカード（選択モードでも展開しない・クリックでグループ一括選択） */}
                            {groups.length > 0 && (
                                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3">
                                    {groups.map((group) => {
                                        const allGroupSelected = group.books.every((b) =>
                                            selectedNames.has(b.name),
                                        );
                                        const partialGroupSelected =
                                            !allGroupSelected &&
                                            group.books.some((b) => selectedNames.has(b.name));
                                        return (
                                            <SeriesGroupCard
                                                key={group.label}
                                                group={group}
                                                groupMode={groupMode}
                                                onClick={() =>
                                                    group.series_id
                                                        ? handleGroupClick(group.series_id)
                                                        : undefined
                                                }
                                                isSelecting={isSelecting}
                                                selectionState={
                                                    allGroupSelected
                                                        ? 'all'
                                                        : partialGroupSelected
                                                          ? 'partial'
                                                          : 'none'
                                                }
                                                onSelect={() => toggleGroupSelect(group)}
                                            />
                                        );
                                    })}
                                </div>
                            )}

                            {/* グループ外（未設定）書籍 */}
                            {ungrouped.length > 0 && (
                                <div>
                                    <p className="text-xs text-gray-400 dark:text-gray-500 mb-2">
                                        {groupMode === 'author' ? '作者未設定' : 'シリーズ未設定'}（
                                        {ungrouped.length} 冊）
                                    </p>
                                    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3">
                                        {ungrouped.map(renderCard)}
                                    </div>
                                </div>
                            )}
                        </div>
                    )}
                </>
            )}

            {/* ダイアログ */}
            <NovelBulkAuthorDialog
                open={showAuthorDialog}
                targetCount={selectedList.length}
                allAuthors={allAuthors}
                onClose={() => setShowAuthorDialog(false)}
                onApply={handleApplyAuthors}
            />
            <NovelBulkSeriesAssignDialog
                open={showSeriesDialog}
                selectedBooks={selectedList}
                allSeries={allSeriesForDialog}
                allBooks={books}
                onClose={() => setShowSeriesDialog(false)}
                onAssign={handleAssignSeries}
            />
        </section>
    );
}
