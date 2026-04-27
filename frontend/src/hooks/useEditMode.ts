import { useState, useCallback } from 'react';
import type { LibrarySource, DeletePagesResponse } from '../types';
import { API_ENDPOINTS } from '../config/api';
import apiClient from '../config/api_client';

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
}

/**
 * リーダーの編集モード（ページ選択 + 削除）を管理するフック。
 *
 * - 削除確認は呼び出し側で `<ConfirmDialog>` をレンダリングする想定。
 * - 確認後は `confirmDeletePages()` を呼んで API 削除を実行する。
 */
export function useEditMode({
    selectedPdf, currentPath, currentSource,
    pageNumber, setPageNumber, onPdfUpdated, bumpPdfVersion, showError,
}: UseEditModeProps): UseEditModeReturn {
    const [isEditMode, setIsEditMode] = useState(false);
    const [selectedPages, setSelectedPages] = useState<Set<number>>(new Set());
    const [pendingDeleteCount, setPendingDeleteCount] = useState(0);

    const toggleEditMode = useCallback(() => {
        setIsEditMode(prev => !prev);
        setSelectedPages(new Set());
    }, []);

    const togglePageSelection = useCallback((pNum: number, e: React.MouseEvent) => {
        e.stopPropagation();
        setSelectedPages(prev => {
            const next = new Set(prev);
            if (next.has(pNum)) next.delete(pNum);
            else next.add(pNum);
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
            const pageIndices = Array.from(selectedPages).map(p => p - 1);
            const data = await apiClient.post<unknown, DeletePagesResponse>(
                API_ENDPOINTS.DELETE_PAGES(selectedPdf, currentPath, currentSource),
                { page_indices: pageIndices }
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
            showError(e instanceof Error ? e.message : '削除に失敗しました。');
        }
    }, [selectedPages, selectedPdf, currentPath, currentSource, pageNumber, setPageNumber, onPdfUpdated, bumpPdfVersion, showError]);

    return {
        isEditMode, selectedPages,
        toggleEditMode, togglePageSelection, resetEditMode,
        requestDeletePages, confirmDeletePages, cancelDeletePages,
        pendingDeleteCount,
    };
}
