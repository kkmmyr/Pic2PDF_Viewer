import { useCallback, useMemo } from 'react';
import type { LibrarySource, RegenerateThumbnailBulkResponse, MergePdfsResponse } from '../types';
import { API_ENDPOINTS } from '../config/api';
import apiClient from '../config/api_client';
import type { ToastType } from './useToast';

/**
 * `useBookMeta` から渡すアクション関数群（必要分のみ）。
 */
export interface BookMetaActions {
    updateAuthors: (path: string, names: string[], authors: string[]) => Promise<void>;
    updateTags: (path: string, names: string[], tags: string[]) => Promise<void>;
    setHidden: (path: string, names: string[], hidden: boolean) => Promise<void>;
    assignSeries: (path: string, names: string[], params: { title: string; index: number | number[]; id?: string }) => Promise<string>;
    reorderSeries: (path: string, names: string[], seriesId: string) => Promise<void>;
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
    showToast: (message: string, type?: ToastType) => void;
}

/**
 * ライブラリの一括操作 7 種をまとめて提供する。
 * - エラー時はトーストで通知し、成功時は選択モードを解除する（共通の後処理）
 * - PDF 限定の操作（tags / hidden bulk / thumbnail / merge / series）はファイル名で `.pdf` フィルタを掛ける
 */
export function useLibraryBulkActions({
    currentPath, currentSource, selectedItems, showHidden, seriesFilter,
    onClearSelection, onRefresh, bookMeta, showToast,
}: UseLibraryBulkActionsOptions) {
    /** 選択中の PDF 名のみ抽出（`.pdf` 以外は除外） */
    const selectedPdfNames = useMemo(
        () => Array.from(selectedItems).filter(item => item.toLowerCase().endsWith('.pdf')),
        [selectedItems]
    );

    /** 一括シリーズ登録は選択順を維持する必要があるため、Set のイテレーション順をそのまま使う */
    const bulkSeriesNames = selectedPdfNames;

    const handleBulkApplyAuthors = useCallback(async (authors: string[]) => {
        await bookMeta.updateAuthors(currentPath, Array.from(selectedItems), authors);
        onClearSelection();
    }, [bookMeta, currentPath, selectedItems, onClearSelection]);

    const handleBulkApplyTags = useCallback(async (tags: string[]) => {
        await bookMeta.updateTags(currentPath, selectedPdfNames, tags);
        onClearSelection();
    }, [bookMeta, currentPath, selectedPdfNames, onClearSelection]);

    /** 1冊だけの非表示/再表示。`showHidden` モード時は逆操作（再表示） */
    const handleToggleHiddenOne = useCallback(async (name: string) => {
        try {
            await bookMeta.setHidden(currentPath, [name], !showHidden);
        } catch (e: unknown) {
            showToast(e instanceof Error ? e.message : '更新に失敗しました。', 'error');
        }
    }, [bookMeta, currentPath, showHidden, showToast]);

    const handleBulkToggleHidden = useCallback(async () => {
        if (selectedPdfNames.length === 0) return;
        try {
            await bookMeta.setHidden(currentPath, selectedPdfNames, !showHidden);
            onClearSelection();
        } catch (e: unknown) {
            showToast(e instanceof Error ? e.message : '更新に失敗しました。', 'error');
        }
    }, [bookMeta, currentPath, selectedPdfNames, showHidden, showToast, onClearSelection]);

    const handleRegenThumbnailBulk = useCallback(async () => {
        if (selectedPdfNames.length === 0) return;
        try {
            const data = await apiClient.post<unknown, RegenerateThumbnailBulkResponse>(
                API_ENDPOINTS.REGENERATE_THUMBNAIL_BULK,
                { names: selectedPdfNames, path: currentPath, source: currentSource }
            );
            onRefresh();
            if (data.failed.length > 0) {
                showToast(`${data.succeeded.length} 件再生成完了。失敗: ${data.failed.join(', ')}`, 'error');
            }
            // 部分失敗があっても、成功した分はあるので選択は解除する（押し直しの意図がない）
            onClearSelection();
        } catch (e: unknown) {
            showToast(e instanceof Error ? e.message : 'サムネイル再生成に失敗しました。', 'error');
        }
    }, [selectedPdfNames, currentPath, currentSource, onRefresh, onClearSelection, showToast]);

    const handleMergePdfs = useCallback(async (outputName: string) => {
        await apiClient.post<unknown, MergePdfsResponse>(
            API_ENDPOINTS.MERGE_PDFS,
            { names: selectedPdfNames, output_name: outputName, path: currentPath, source: currentSource }
        );
        onRefresh();
        onClearSelection();
    }, [selectedPdfNames, currentPath, currentSource, onRefresh, onClearSelection]);

    /** シリーズドリルダウン中の DnD ドロップで呼ばれる。`useBookMeta.reorderSeries` 内で楽観的更新+ロールバック実装済み */
    const handleSeriesReorder = useCallback(async (newOrder: string[]) => {
        if (!seriesFilter || newOrder.length === 0) return;
        try {
            await bookMeta.reorderSeries(currentPath, newOrder, seriesFilter);
        } catch (e: unknown) {
            showToast(e instanceof Error ? e.message : '並べ替えに失敗しました。', 'error');
        }
    }, [seriesFilter, currentPath, bookMeta, showToast]);

    const handleBulkDelete = useCallback(async () => {
        if (selectedPdfNames.length === 0) return;
        const ok = window.confirm(
            `選択した ${selectedPdfNames.length} 件をディスクから完全に削除しますか？\nこの操作は元に戻せません。`
        );
        if (!ok) return;
        try {
            await apiClient.delete(API_ENDPOINTS.DELETE_PDFS, {
                data: { names: selectedPdfNames, path: currentPath, source: currentSource }
            });
            onRefresh();
            onClearSelection();
            showToast(`${selectedPdfNames.length} 件を削除しました`, 'success');
        } catch (e: unknown) {
            showToast(e instanceof Error ? e.message : '削除に失敗しました。', 'error');
        }
    }, [selectedPdfNames, currentPath, currentSource, onRefresh, onClearSelection, showToast]);

    const handleBulkAssignSeries = useCallback(async (params: { title: string; indexes: number[]; id?: string }) => {
        if (bulkSeriesNames.length === 0) return;
        if (params.indexes.length !== bulkSeriesNames.length) {
            throw new Error('採番リストが選択数と一致しません');
        }
        try {
            await bookMeta.assignSeries(currentPath, bulkSeriesNames, {
                title: params.title,
                index: params.indexes,
                id: params.id,
            });
            showToast(`${bulkSeriesNames.length} 冊を「${params.title}」に登録しました`, 'success');
            onClearSelection();
        } catch (e: unknown) {
            showToast(e instanceof Error ? e.message : 'シリーズ登録に失敗しました。', 'error');
            throw e;
        }
    }, [bookMeta, currentPath, bulkSeriesNames, showToast, onClearSelection]);

    return {
        bulkSeriesNames,
        handleBulkApplyAuthors,
        handleBulkApplyTags,
        handleToggleHiddenOne,
        handleBulkToggleHidden,
        handleBulkDelete,
        handleRegenThumbnailBulk,
        handleMergePdfs,
        handleSeriesReorder,
        handleBulkAssignSeries,
    };
}
