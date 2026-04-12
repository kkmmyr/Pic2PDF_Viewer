import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import type { LibrarySource } from '../types';

/**
 * ViewerPage の URL パラメータ同期ロジックを一元管理するフック。
 *
 * searchParams から currentPath / selectedPdf を導出し、
 * ナビゲーション操作を提供することで ViewerPage の状態二重管理を排除する。
 */
export function useUrlState() {
    const [searchParams, setSearchParams] = useSearchParams();

    const currentPath = searchParams.get('path') || '';
    const selectedPdf = searchParams.get('file') || null;

    /** フォルダに入る */
    const navigateIntoFolder = useCallback((dirName: string, basePath: string) => {
        const newPath = basePath ? `${basePath}/${dirName}` : dirName;
        setSearchParams({ path: newPath });
    }, [setSearchParams]);

    /** 一つ上のフォルダへ戻る */
    const navigateUp = useCallback((currentPath: string) => {
        if (!currentPath) return;
        const parts = currentPath.split('/');
        parts.pop();
        const newPath = parts.join('/');
        const newParams = new URLSearchParams();
        if (newPath) newParams.set('path', newPath);
        setSearchParams(newParams);
    }, [setSearchParams]);

    /** PDF を選択する */
    const selectPdf = useCallback((pdfName: string, currentPath: string) => {
        const params: Record<string, string> = { file: pdfName };
        if (currentPath) params.path = currentPath;
        setSearchParams(params);
    }, [setSearchParams]);

    /** PDF の選択を解除する（ライブラリに戻る） */
    const clearPdf = useCallback((currentPath: string) => {
        const newParams = new URLSearchParams();
        if (currentPath) newParams.set('path', currentPath);
        setSearchParams(newParams);
    }, [setSearchParams]);

    /** ソース切り替え時にすべてのパラメータをリセットする */
    const resetAll = useCallback(() => {
        setSearchParams({});
    }, [setSearchParams]);

    return {
        currentPath,
        selectedPdf,
        navigateIntoFolder,
        navigateUp,
        selectPdf,
        clearPdf,
        resetAll,
    };
}
