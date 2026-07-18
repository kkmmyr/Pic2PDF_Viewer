import { useCallback, useMemo } from 'react';
import { toast } from 'sonner';
import type { LibrarySource, RegenerateThumbnailBulkResponse, MergePdfsResponse } from '@/types';
import { API_ENDPOINTS } from '@/config/api';
import apiClient from '@/config/api_client';
import { useAsyncToast } from '@/hooks/useAsyncToast';

/**
 * `useBookMeta` から渡すアクション関数群（必要分のみ）。
 */
interface BookMetaActions {
    updateAuthors: (path: string, names: string[], authors: string[]) => Promise<void>;
    updateGenre: (path: string, names: string[], genre: string) => Promise<void>;
    setHidden: (path: string, names: string[], hidden: boolean) => Promise<void>;
    assignSeries: (
        path: string,
        names: string[],
        params: { title: string; index: number | number[]; id?: string },
    ) => Promise<string>;
    unassignSeries: (path: string, names: string[]) => Promise<void>;
    reorderSeries: (path: string, names: string[], seriesId: string) => Promise<void>;
}

interface SeriesAssignParams {
    mode: 'existing' | 'new' | 'remove';
    seriesId?: string;
    seriesTitle?: string;
    indexes?: number[];
}

interface UseLibraryBulkActionsOptions {
    currentPath: string;
    currentSource: LibrarySource;
    selectedItems: Set<string>;
    showHidden: boolean;
    seriesFilter: string;
    onClearSelection: () => void;
    onRefresh: () => void;
    bookMeta: BookMetaActions;
    addGenre: (name: string) => Promise<void>;
    currentGenres: string[];
}

/**
 * ライブラリの一括操作をまとめて提供する。
 * - エラー時はトーストで通知し、成功時は選択モードを解除する（共通の後処理）
 * - PDF 限定の操作（hidden bulk / thumbnail / merge / series）はファイル名で `.pdf` フィルタを掛ける
 */
export function useLibraryBulkActions({
    currentPath,
    currentSource,
    selectedItems,
    showHidden,
    seriesFilter,
    onClearSelection,
    onRefresh,
    bookMeta,
    addGenre,
    currentGenres,
}: UseLibraryBulkActionsOptions) {
    const runAsync = useAsyncToast();

    /** 選択中の PDF 名のみ抽出（`.pdf` 以外は除外） */
    const selectedPdfNames = useMemo(
        () => Array.from(selectedItems).filter((item) => item.toLowerCase().endsWith('.pdf')),
        [selectedItems],
    );

    /** 一括シリーズ登録は選択順を維持する必要があるため、Set のイテレーション順をそのまま使う */
    const bulkSeriesNames = selectedPdfNames;

    const handleBulkApplyAuthors = useCallback(
        async (authors: string[]) => {
            await bookMeta.updateAuthors(currentPath, Array.from(selectedItems), authors);
            onClearSelection();
        },
        [bookMeta, currentPath, selectedItems, onClearSelection],
    );

    const handleBulkApplyGenre = useCallback(
        async (genre: string) => {
            if (!currentGenres.includes(genre)) {
                await addGenre(genre);
            }
            await bookMeta.updateGenre(currentPath, selectedPdfNames, genre);
            onClearSelection();
        },
        [bookMeta, currentPath, selectedPdfNames, onClearSelection, addGenre, currentGenres],
    );

    /** 1冊だけの非表示/再表示。`showHidden` モード時は逆操作（再表示） */
    const handleToggleHiddenOne = useCallback(
        async (name: string) => {
            await runAsync(
                () => bookMeta.setHidden(currentPath, [name], !showHidden),
                '更新に失敗しました。',
            );
        },
        [bookMeta, currentPath, showHidden, runAsync],
    );

    const handleBulkToggleHidden = useCallback(async () => {
        if (selectedPdfNames.length === 0) return;
        const ok = await runAsync(async () => {
            await bookMeta.setHidden(currentPath, selectedPdfNames, !showHidden);
            return true;
        }, '更新に失敗しました。');
        if (ok) onClearSelection();
    }, [bookMeta, currentPath, selectedPdfNames, showHidden, runAsync, onClearSelection]);

    const handleRegenThumbnailBulk = useCallback(async () => {
        if (selectedPdfNames.length === 0) return;
        const data = await runAsync(
            () =>
                apiClient.post<unknown, RegenerateThumbnailBulkResponse>(
                    API_ENDPOINTS.REGENERATE_THUMBNAIL_BULK,
                    { names: selectedPdfNames, path: currentPath, source: currentSource },
                ),
            'サムネイル再生成に失敗しました。',
        );
        if (!data) return;
        onRefresh();
        if (data.failed.length > 0) {
            toast.error(`${data.succeeded.length} 件再生成完了。失敗: ${data.failed.join(', ')}`);
        }
        onClearSelection();
    }, [selectedPdfNames, currentPath, currentSource, onRefresh, onClearSelection, runAsync]);

    const handleMergePdfs = useCallback(
        async (outputName: string) => {
            await apiClient.post<unknown, MergePdfsResponse>(API_ENDPOINTS.MERGE_PDFS, {
                names: selectedPdfNames,
                output_name: outputName,
                path: currentPath,
                source: currentSource,
            });
            onRefresh();
            onClearSelection();
        },
        [selectedPdfNames, currentPath, currentSource, onRefresh, onClearSelection],
    );

    /** シリーズドリルダウン中の DnD ドロップで呼ばれる。`useBookMeta.reorderSeries` 内で楽観的更新+ロールバック実装済み */
    const handleSeriesReorder = useCallback(
        async (newOrder: string[]) => {
            if (!seriesFilter || newOrder.length === 0) return;
            await runAsync(
                () => bookMeta.reorderSeries(currentPath, newOrder, seriesFilter),
                '並べ替えに失敗しました。',
            );
        },
        [seriesFilter, currentPath, bookMeta, runAsync],
    );

    const handleBulkDelete = useCallback(async () => {
        if (selectedPdfNames.length === 0) return;
        const ok = await runAsync(async () => {
            await apiClient.delete(API_ENDPOINTS.DELETE_PDFS, {
                data: { names: selectedPdfNames, path: currentPath, source: currentSource },
            });
            return true;
        }, '削除に失敗しました。');
        if (!ok) return;
        onRefresh();
        onClearSelection();
        toast.success(`${selectedPdfNames.length} 件を削除しました`);
    }, [selectedPdfNames, currentPath, currentSource, onRefresh, onClearSelection, runAsync]);

    const handleBulkAssignSeries = useCallback(
        async (params: SeriesAssignParams) => {
            if (bulkSeriesNames.length === 0) return;
            if (params.mode === 'remove') {
                await runAsync(
                    () => bookMeta.unassignSeries(currentPath, bulkSeriesNames),
                    'シリーズ解除に失敗しました。',
                    { rethrow: true },
                );
                toast.success(`${bulkSeriesNames.length} 冊をシリーズから外しました`);
            } else {
                const title = params.seriesTitle ?? '';
                const indexes = params.indexes ?? [];
                if (indexes.length !== bulkSeriesNames.length) {
                    throw new Error('採番リストが選択数と一致しません');
                }
                await runAsync(
                    () =>
                        bookMeta.assignSeries(currentPath, bulkSeriesNames, {
                            title,
                            index: indexes,
                            id: params.seriesId,
                        }),
                    'シリーズ登録に失敗しました。',
                    { rethrow: true },
                );
                toast.success(`${bulkSeriesNames.length} 冊を「${title}」に登録しました`);
            }
            onClearSelection();
        },
        [bookMeta, currentPath, bulkSeriesNames, runAsync, onClearSelection],
    );

    return {
        bulkSeriesNames,
        handleBulkApplyAuthors,
        handleBulkApplyGenre,
        handleToggleHiddenOne,
        handleBulkToggleHidden,
        handleBulkDelete,
        handleRegenThumbnailBulk,
        handleMergePdfs,
        handleSeriesReorder,
        handleBulkAssignSeries,
    };
}
