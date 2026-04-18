import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import type { LibrarySource } from '../types';

const VALID_SOURCES: LibrarySource[] = ['generated', 'kindle', 'novel'];

/**
 * ViewerPage の URL パラメータ同期ロジックを一元管理するフック。
 *
 * searchParams から currentPath / selectedPdf / currentSource を導出し、
 * ナビゲーション操作を提供する。source も URL に含めることで
 * リロード・直接アクセス時にも正しいソースが復元される。
 */
export function useUrlState() {
    const [searchParams, setSearchParams] = useSearchParams();

    const currentPath = searchParams.get('path') || '';
    const selectedPdf = searchParams.get('file') || null;
    const rawSource = searchParams.get('source') || 'generated';
    const currentSource: LibrarySource = VALID_SOURCES.includes(rawSource as LibrarySource)
        ? (rawSource as LibrarySource)
        : 'generated';

    /** フォルダに入る */
    const navigateIntoFolder = useCallback((dirName: string, basePath: string, source: LibrarySource) => {
        const newPath = basePath ? `${basePath}/${dirName}` : dirName;
        const params: Record<string, string> = { path: newPath, source };
        setSearchParams(params);
    }, [setSearchParams]);

    /** 一つ上のフォルダへ戻る */
    const navigateUp = useCallback((currentPath: string, source: LibrarySource) => {
        if (!currentPath) return;
        const parts = currentPath.split('/');
        parts.pop();
        const newPath = parts.join('/');
        const newParams = new URLSearchParams();
        if (newPath) newParams.set('path', newPath);
        newParams.set('source', source);
        setSearchParams(newParams);
    }, [setSearchParams]);

    /** PDF を選択する */
    const selectPdf = useCallback((pdfName: string, currentPath: string, source: LibrarySource) => {
        const params: Record<string, string> = { file: pdfName, source };
        if (currentPath) params.path = currentPath;
        setSearchParams(params);
    }, [setSearchParams]);

    /** PDF の選択を解除する（ライブラリに戻る） */
    const clearPdf = useCallback((currentPath: string, source: LibrarySource) => {
        const newParams = new URLSearchParams();
        if (currentPath) newParams.set('path', currentPath);
        newParams.set('source', source);
        setSearchParams(newParams);
    }, [setSearchParams]);

    /** ソース切り替え時にソースだけ変更してパス・ファイルをリセット */
    const setSource = useCallback((source: LibrarySource) => {
        setSearchParams({ source });
    }, [setSearchParams]);

    return {
        currentPath,
        selectedPdf,
        currentSource,
        navigateIntoFolder,
        navigateUp,
        selectPdf,
        clearPdf,
        setSource,
    };
}
