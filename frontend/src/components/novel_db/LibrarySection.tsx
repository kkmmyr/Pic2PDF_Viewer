/**
 * ライブラリ（書籍一覧）セクション。
 *
 * - トップ階層: シリーズ/作者グループカードグリッド + 未設定書籍フラット表示
 * - ドリルダウン: シリーズ内 DnD 並び替え（ドロップ時即時保存）
 * - 選択モード: フラット/グループ/ドリルダウン全モードで利用可（一括作者設定 / 一括シリーズ登録）
 */
import { useState, useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Check } from 'lucide-react';

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
import { LibraryViewModeSelector } from './LibraryViewModeSelector';
import { BulkActionsPanel } from './BulkActionsPanel';
import { SeriesDrilldownPanel } from './SeriesDrilldownPanel';

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
    const [searchParams, setSearchParams] = useSearchParams();
    const [groupMode, setGroupMode] = useState<GroupMode>('series');
    const [isSelecting, setIsSelecting] = useState(false);
    const [selectedNames, setSelectedNames] = useState<Set<string>>(new Set());

    const [showAuthorDialog, setShowAuthorDialog] = useState(false);
    const [showSeriesDialog, setShowSeriesDialog] = useState(false);
    const [allAuthors, setAllAuthors] = useState<string[]>([]);
    const [allSeriesForDialog, setAllSeriesForDialog] = useState<SeriesSummary[]>([]);

    const { groups, ungrouped } = useNovelLibraryGroup(books, groupMode);

    const drilldownId = searchParams.get('dd');
    const drilldown = useMemo(() => {
        if (!drilldownId) return null;
        const group = groups.find((g) => g.series_id === drilldownId);
        if (!group) return null;
        return { seriesId: group.series_id!, label: group.label, books: group.books };
    }, [drilldownId, groups]);

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

    const toggleSelecting = useCallback(() => {
        if (isSelecting) exitSelecting();
        else setIsSelecting(true);
    }, [isSelecting, exitSelecting]);

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

    const handleApplyAuthors = async (authors: string[]) => {
        const targets = books.filter((b) => selectedNames.has(b.name));
        for (const book of targets) {
            await patchNovelBookMeta(`${book.name}.pdf`, { authors });
        }
        onMetaRefetch();
        exitSelecting();
    };

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

    return (
        <section className="space-y-3">
            {drilldown ? (
                <SeriesDrilldownPanel
                    drilldown={drilldown}
                    isSelecting={isSelecting}
                    selectedNames={selectedNames}
                    renderCard={renderCard}
                    onBack={handleBackToLibrary}
                    onToggleSelecting={toggleSelecting}
                    onToggleSelectAll={toggleSelectAll}
                    onOpenAuthorDialog={() => void openAuthorDialog()}
                    onOpenSeriesDialog={() => void openSeriesDialog()}
                    onOpenDetailBook={onOpenDetailBook}
                    onEditBook={onEditBook}
                    onReordered={onMetaRefetch}
                />
            ) : (
                <>
                    <LibraryViewModeSelector
                        groupMode={groupMode}
                        totalCount={books.length}
                        isSelecting={isSelecting}
                        onChangeMode={setGroupMode}
                        onToggleSelecting={toggleSelecting}
                    />

                    {isSelecting && (
                        <BulkActionsPanel
                            targetBooks={books}
                            selectedNames={selectedNames}
                            onToggleSelectAll={toggleSelectAll}
                            onOpenAuthorDialog={() => void openAuthorDialog()}
                            onOpenSeriesDialog={() => void openSeriesDialog()}
                        />
                    )}

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
