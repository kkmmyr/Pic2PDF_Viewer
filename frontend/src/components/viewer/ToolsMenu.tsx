import { useEffect, useRef, useState } from 'react';
import { Settings, ChevronDown } from 'lucide-react';
import { AutoFillAuthorsBar } from './AutoFillAuthorsBar';
import { SeriesResolveBar } from './SeriesResolveBar';
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
export function ToolsMenu({ source, onComplete }: ToolsMenuProps) {
    const [open, setOpen] = useState(false);
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
                    <AutoFillAuthorsBar source={source} onComplete={onComplete} />
                    <SeriesResolveBar source={source} onComplete={onComplete} />
                </div>
            )}
        </div>
    );
}
