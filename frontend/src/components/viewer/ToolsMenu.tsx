import { useEffect, useRef, useState } from 'react';
import { Settings, ChevronDown, Download } from 'lucide-react';
import { AutoFillAuthorsBar } from './AutoFillAuthorsBar';
import { SeriesResolveBar } from './SeriesResolveBar';
import { API_ENDPOINTS, buildApiUrl } from '../../config/api';
import type { LibrarySource } from '../../types';

interface ToolsMenuProps {
    source: LibrarySource;
    onComplete: () => void;
}

/**
 * Library 画面ヘッダーの「ツール ▼」ドロップダウン。
 * 滅多に使わないジョブ起動 UI（サークル名自動登録 / シリーズ判定）を集約し、
 * 常時表示で画面を圧迫しないようにする。
 */
async function downloadMetaExport(source: LibrarySource): Promise<void> {
    const url = buildApiUrl(API_ENDPOINTS.META_EXPORT(source));
    const res = await fetch(url);
    if (!res.ok) throw new Error(`export failed: ${res.status}`);
    const blob = await res.blob();
    const filename = res.headers.get('Content-Disposition')?.match(/filename="([^"]+)"/)?.[1]
        ?? `meta_${source}.json`;
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
    URL.revokeObjectURL(a.href);
}

export function ToolsMenu({ source, onComplete }: ToolsMenuProps) {
    const [open, setOpen] = useState(false);
    const [exporting, setExporting] = useState(false);
    const containerRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (!open) return;
        const handleMouseDown = (e: MouseEvent) => {
            if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
                setOpen(false);
            }
        };
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === 'Escape') setOpen(false);
        };
        document.addEventListener('mousedown', handleMouseDown);
        document.addEventListener('keydown', handleKeyDown);
        return () => {
            document.removeEventListener('mousedown', handleMouseDown);
            document.removeEventListener('keydown', handleKeyDown);
        };
    }, [open]);

    return (
        <div ref={containerRef} className="relative">
            <button
                onClick={() => setOpen(o => !o)}
                title="自動登録・シリーズ判定などのバッチ処理"
                className="px-3 py-1.5 bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 rounded-md text-sm font-medium hover:bg-gray-200 dark:hover:bg-gray-700 flex items-center gap-1.5"
            >
                <Settings className="w-4 h-4" />
                ツール
                <ChevronDown className={`w-3.5 h-3.5 transition-transform ${open ? 'rotate-180' : ''}`} />
            </button>
            {open && (
                <div className="absolute right-0 top-full mt-1 w-[520px] bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-md shadow-lg overflow-hidden">
                    <div className="flex items-center justify-between gap-3 px-4 py-2.5 border-b border-gray-100 dark:border-gray-700">
                        <span className="text-sm text-gray-600 dark:text-gray-400">メタデータ（著者・タグ・シリーズ等）をバックアップ</span>
                        <button
                            onClick={async () => {
                                setExporting(true);
                                try { await downloadMetaExport(source); }
                                finally { setExporting(false); }
                            }}
                            disabled={exporting}
                            className="flex items-center gap-1.5 px-3 py-1 text-sm bg-primary-600 hover:bg-primary-700 disabled:opacity-60 text-white rounded-md shrink-0"
                        >
                            <Download className="w-3.5 h-3.5" />
                            {exporting ? 'エクスポート中...' : 'エクスポート'}
                        </button>
                    </div>
                    <AutoFillAuthorsBar source={source} onComplete={onComplete} />
                    <SeriesResolveBar source={source} onComplete={onComplete} />
                </div>
            )}
        </div>
    );
}
