import { useState } from 'react';
import { Download, Loader2 } from 'lucide-react';

import { API_ENDPOINTS } from '../../config/api';
import apiClient from '../../config/api_client';

interface Props {
    showToast: (message: string, type: 'success' | 'error') => void;
}

/**
 * Amazon CSV インポートボタン。novel + comic の 2 ソースを同時インポートする。
 * インポート結果は showToast を通じて親コンポーネントのトーストに表示する。
 */
export function AmazonImportButton({ showToast }: Props) {
    const [isImporting, setIsImporting] = useState(false);

    const handleImport = async () => {
        setIsImporting(true);
        try {
            const [novelRes, comicRes] = await Promise.allSettled([
                apiClient.post<{ updated: number; skipped: number; unmatched: number }>(
                    API_ENDPOINTS.AMAZON_IMPORT('novel'),
                ),
                apiClient.post<{ updated: number; skipped: number; unmatched: number }>(
                    API_ENDPOINTS.AMAZON_IMPORT('comic'),
                ),
            ]);

            const novelData = novelRes.status === 'fulfilled' ? novelRes.value.data : null;
            const comicData = comicRes.status === 'fulfilled' ? comicRes.value.data : null;

            const updated = (novelData?.updated ?? 0) + (comicData?.updated ?? 0);
            const skipped = (novelData?.skipped ?? 0) + (comicData?.skipped ?? 0);
            const unmatched = (novelData?.unmatched ?? 0) + (comicData?.unmatched ?? 0);
            const hasError =
                novelRes.status === 'rejected' || comicRes.status === 'rejected';

            if (hasError && updated === 0) {
                const msg =
                    novelRes.status === 'rejected'
                        ? (novelRes.reason as Error).message
                        : (comicRes.reason as Error).message;
                showToast(`インポート失敗: ${msg}`, 'error');
            } else {
                showToast(
                    `更新: ${updated} 件 / スキップ: ${skipped} 件 / 未マッチ: ${unmatched} 件`,
                    'success',
                );
            }
        } finally {
            setIsImporting(false);
        }
    };

    return (
        <button
            onClick={() => void handleImport()}
            disabled={isImporting}
            className="flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50 transition-colors"
            title="Amazon CSV から著者・ASIN を補完（novel + comic）"
        >
            {isImporting ? (
                <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
                <Download className="w-4 h-4" />
            )}
            Amazon CSV
        </button>
    );
}
