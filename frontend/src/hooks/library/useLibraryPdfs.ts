import { useQuery } from '@tanstack/react-query';
import type { LibrarySource, PdfFile } from '@/types';
import { API_ENDPOINTS } from '@/config/api';
import apiClient from '@/config/api_client';

export const pdfQueryKey = (path: string, source: LibrarySource) => ['pdfs', path, source] as const;

/**
 * PDF 一覧取得フック。
 *
 * React Query キャッシュ ['pdfs', path, source] で管理する。
 * リネーム・削除・生成完了などの書き込み操作後は呼び出し元が
 * `queryClient.invalidateQueries({ queryKey: pdfQueryKey(path, source) })` で
 * 再取得をトリガーする。
 */
export function useLibraryPdfs(path: string, source: LibrarySource) {
    return useQuery<PdfFile[]>({
        queryKey: pdfQueryKey(path, source),
        queryFn: async () => {
            try {
                const data = await apiClient.get<unknown, { files: PdfFile[] }>(
                    API_ENDPOINTS.PDFS,
                    { params: { path, source } },
                );
                return data.files ?? [];
            } catch {
                return [];
            }
        },
    });
}
