/**
 * novel_db タブのサブヘッダー。スコープ選択 + 全件再構築ボタン。
 */
import { RefreshCw } from 'lucide-react';

import type {
    BookSummary,
    RebuildStatus,
    Scope,
    SeriesSummary,
} from '../../features/novel_db/types';

import ScopeSelector from './ScopeSelector';

interface Props {
    scope: Scope;
    onScopeChange: (s: Scope) => void;
    books: BookSummary[];
    series: SeriesSummary[];
    onRebuildAll: () => void;
    rebuildStatus: RebuildStatus | null;
}

export default function NovelDbHeader({
    scope,
    onScopeChange,
    books,
    series,
    onRebuildAll,
    rebuildStatus,
}: Props) {
    const isLocked = rebuildStatus?.is_running ?? false;
    return (
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-4 border-b border-gray-200 dark:border-gray-700">
            <div>
                <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                    小説テキスト検索
                </h1>
                <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                    novel ソースの OCR テキストを横断検索・RAG 質問応答
                </p>
            </div>
            <div className="flex items-center gap-3">
                <ScopeSelector
                    scope={scope}
                    onChange={onScopeChange}
                    books={books}
                    series={series}
                />
                <button
                    onClick={onRebuildAll}
                    disabled={isLocked}
                    className="px-3 py-1.5 text-sm rounded-md bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5"
                    title="全書籍を順次再構築する"
                >
                    <RefreshCw className="w-4 h-4" />
                    全件再構築
                </button>
            </div>
        </div>
    );
}
