import { Download, Loader2 } from 'lucide-react';
import { toast } from 'sonner';

import { useAmazonImport } from '@/hooks/library/useAmazonImport';

export function AmazonImportButton() {
    const { importAmazon, isImporting } = useAmazonImport();

    const handleImport = async () => {
        const result = await importAmazon();
        if (result.hasError && result.updated === 0) {
            toast.error(`インポート失敗: ${result.errorMessage ?? '不明なエラー'}`);
        } else {
            toast.success(
                `更新: ${result.updated} 件 / スキップ: ${result.skipped} 件 / 未マッチ: ${result.unmatched} 件`,
            );
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
