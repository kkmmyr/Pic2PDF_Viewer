import { useState, useCallback } from 'react';
import type { LibrarySource, DeletePagesResponse } from '../../types';
import { API_ENDPOINTS } from '../../config/api';
import apiClient from '../../config/api_client';
import { errorMessage } from '../../utils/error';

interface UseEditModeProps {
    selectedPdf: string;
    currentPath: string;
    currentSource: LibrarySource;
    pageNumber: number;
    setPageNumber: (page: number) => void;
    onPdfUpdated: () => void;
    /** PDF 再描画用のバージョンを進めるコールバック */
    bumpPdfVersion: () => void;
    showError: (message: string) => void;
}

interface UseEditModeReturn {
    isEditMode: boolean;
    selectedPages: Set<number>;
    toggleEditMode: () => void;
    togglePageSelection: (pNum: number, e: React.MouseEvent) => void;
    /** 範囲を選択に追加（Shift+クリック用、from/to は順不同） */
    selectRange: (from: number, to: number) => void;
    /** 編集モード状態を完全リセット（PDF切り替え時用） */
    resetEditMode: () => void;
    /** 削除を要求（確認ダイアログを開かせる）。表示は呼び出し側で */
    requestDeletePages: () => void;
    /** 確認後に実際に削除を実行する */
    confirmDeletePages: () => Promise<void>;
    /** 削除リクエストをキャンセル */
    cancelDeletePages: () => void;
    /** 0 でない場合は削除確認ダイアログを開くべき */
    pendingDeleteCount: number;
    /**
     * ページを並び替える（B-3）。
     * `newOrder[i]` は新しい位置 i+1 に配置する元の 1 始まりページ番号。
     * 成功時に selectedPages を新位置に追従させ、`bumpPdfVersion()` を呼ぶ。
     * 戻り値: 成功なら true / 失敗（API エラー）なら false
     */
    applyReorder: (newOrder: number[]) => Promise<boolean>;
}

/**
 * リーダーの編集モード（ページ選択 + 削除）を管理するフック。
 *
 * - 削除確認は呼び出し側で `<ConfirmDialog>` をレンダリングする想定。
 * - 確認後は `confirmDeletePages()` を呼んで API 削除を実行する。
 */
export function useEditMode({
    selectedPdf,
    currentPath,
    currentSource,
    pageNumber,
    setPageNumber,
    onPdfUpdated,
    bumpPdfVersion,
    showError,
}: UseEditModeProps): UseEditModeReturn {
    const [isEditMode, setIsEditMode] = useState(false);
    const [selectedPages, setSelectedPages] = useState<Set<number>>(new Set());
    const [pendingDeleteCount, setPendingDeleteCount] = useState(0);

    const toggleEditMode = useCallback(() => {
        setIsEditMode((prev) => !prev);
        setSelectedPages(new Set());
    }, []);

    const togglePageSelection = useCallback((pNum: number, e: React.MouseEvent) => {
        e.stopPropagation();
        setSelectedPages((prev) => {
            const next = new Set(prev);
            if (next.has(pNum)) next.delete(pNum);
            else next.add(pNum);
            return next;
        });
    }, []);

    const selectRange = useCallback((from: number, to: number) => {
        const min = Math.min(from, to);
        const max = Math.max(from, to);
        setSelectedPages((prev) => {
            const next = new Set(prev);
            for (let p = min; p <= max; p++) next.add(p);
            return next;
        });
    }, []);

    const resetEditMode = useCallback(() => {
        setIsEditMode(false);
        setSelectedPages(new Set());
        setPendingDeleteCount(0);
    }, []);

    const requestDeletePages = useCallback(() => {
        if (selectedPages.size === 0) return;
        setPendingDeleteCount(selectedPages.size);
    }, [selectedPages]);

    const cancelDeletePages = useCallback(() => {
        setPendingDeleteCount(0);
    }, []);

    const confirmDeletePages = useCallback(async () => {
        if (selectedPages.size === 0) {
            setPendingDeleteCount(0);
            return;
        }
        try {
            const pageIndices = Array.from(selectedPages).map((p) => p - 1);
            const data = await apiClient.post<unknown, DeletePagesResponse>(
                API_ENDPOINTS.DELETE_PAGES(selectedPdf, currentPath, currentSource),
                { page_indices: pageIndices },
            );
            setIsEditMode(false);
            setSelectedPages(new Set());
            setPendingDeleteCount(0);
            bumpPdfVersion();
            onPdfUpdated();

            if (pageNumber > data.total_pages) {
                setPageNumber(Math.max(1, data.total_pages));
            }
        } catch (e: unknown) {
            setPendingDeleteCount(0);
            showError(errorMessage(e, '削除に失敗しました。'));
        }
    }, [
        selectedPages,
        selectedPdf,
        currentPath,
        currentSource,
        pageNumber,
        setPageNumber,
        onPdfUpdated,
        bumpPdfVersion,
        showError,
    ]);

    const applyReorder = useCallback(
        async (newOrder: number[]): Promise<boolean> => {
            try {
                await apiClient.post(
                    API_ENDPOINTS.REORDER_PAGES(selectedPdf, currentPath, currentSource),
                    { page_indices: newOrder.map((p) => p - 1) },
                );
                // selectedPages を新位置に追従させる:
                // 旧ページ番号 P が選択されていたら、新位置 newOrder.indexOf(P) + 1 に置き換える
                setSelectedPages((prev) => {
                    if (prev.size === 0) return prev;
                    const next = new Set<number>();
                    for (const oldPage of prev) {
                        const newPos = newOrder.indexOf(oldPage) + 1;
                        if (newPos > 0) next.add(newPos);
                    }
                    return next;
                });
                bumpPdfVersion();
                onPdfUpdated();
                return true;
            } catch (e: unknown) {
                showError(errorMessage(e, '並び替えに失敗しました。'));
                return false;
            }
        },
        [selectedPdf, currentPath, currentSource, bumpPdfVersion, onPdfUpdated, showError],
    );

    return {
        isEditMode,
        selectedPages,
        toggleEditMode,
        togglePageSelection,
        selectRange,
        resetEditMode,
        requestDeletePages,
        confirmDeletePages,
        cancelDeletePages,
        pendingDeleteCount,
        applyReorder,
    };
}
