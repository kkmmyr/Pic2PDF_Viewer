import { useEffect, useRef, useState } from 'react';
import { Settings, ChevronDown, Download } from 'lucide-react';
import { API_ENDPOINTS } from '@/config/api';
import apiClient from '@/config/api_client';
import type { LibrarySource } from '@/types';

interface ToolsMenuProps {
    source: LibrarySource;
    /** 後方互換のため受け取るが現状は未使用（ジョブ系撤去後に残置） */
    onComplete?: () => void;
}

/**
 * Library 画面ヘッダーの「ツール ▼」ドロップダウン。
 * メタデータエクスポートを集約する。
 */
async function downloadMetaExport(source: LibrarySource): Promise<void> {
    // apiClient のレスポンスインターセプタは response.data を返すため、blob が直接得られる。
    // Content-Disposition ヘッダは参照できなくなるが、バックエンドの命名規則
    // (`meta_{source}_{YYYYMMDD}.json`) と同形式をフロント側で生成する。
    const blob = await apiClient.get<unknown, Blob>(API_ENDPOINTS.META_EXPORT(source), {
        responseType: 'blob',
    });
    const today = new Date();
    const dateStr =
        today.getFullYear().toString() +
        String(today.getMonth() + 1).padStart(2, '0') +
        String(today.getDate()).padStart(2, '0');
    const filename = `meta_${source}_${dateStr}.json`;
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
    URL.revokeObjectURL(a.href);
}

export function ToolsMenu({ source }: ToolsMenuProps) {
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
                onClick={() => setOpen((o) => !o)}
                title="メタデータのエクスポート"
                className="px-3 py-1.5 bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 rounded-md text-sm font-medium hover:bg-gray-200 dark:hover:bg-gray-700 flex items-center gap-1.5"
            >
                <Settings className="w-4 h-4" />
                ツール
                <ChevronDown
                    className={`w-3.5 h-3.5 transition-transform ${open ? 'rotate-180' : ''}`}
                />
            </button>
            {open && (
                <div className="absolute right-0 top-full mt-1 w-[520px] bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-md shadow-lg overflow-hidden">
                    <div className="flex items-center justify-between gap-3 px-4 py-2.5">
                        <span className="text-sm text-gray-600 dark:text-gray-400">
                            メタデータ（著者・シリーズ等）をバックアップ
                        </span>
                        <button
                            onClick={async () => {
                                setExporting(true);
                                try {
                                    await downloadMetaExport(source);
                                } finally {
                                    setExporting(false);
                                }
                            }}
                            disabled={exporting}
                            className="flex items-center gap-1.5 px-3 py-1 text-sm bg-primary-600 hover:bg-primary-700 disabled:opacity-60 text-white rounded-md shrink-0"
                        >
                            <Download className="w-3.5 h-3.5" />
                            {exporting ? 'エクスポート中...' : 'エクスポート'}
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
}
