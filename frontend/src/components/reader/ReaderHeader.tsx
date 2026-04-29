import { ArrowLeft, Trash2, CheckSquare, Square, Search, Wand2, BookOpen, FileText, Maximize2, Minimize2, HelpCircle } from 'lucide-react';
import type { ReadingDirection, SpreadMode } from '../../types';

interface ReaderHeaderProps {
    selectedPdf: string;
    direction: ReadingDirection;
    spreadMode: SpreadMode;
    pageNumber: number;
    numPages: number;
    isEditMode: boolean;
    selectedPagesCount: number;
    showHeader: boolean;
    isSearchOpen: boolean;
    isFullscreen: boolean;
    onClose: () => void;
    onToggleDirection: () => void;
    onCycleSpreadMode: () => void;
    onToggleEditMode: () => void;
    onDeletePages: () => void;
    onMouseLeave: () => void;
    onToggleSearch: () => void;
    onToggleFullscreen: () => void;
    onOpenHelp: () => void;
}

const SPREAD_MODE_CONFIG: Record<SpreadMode, { label: string; icon: React.ReactNode; next: SpreadMode }> = {
    auto:   { label: 'Auto',   icon: <Wand2     className="w-4 h-4" />, next: 'spread' },
    spread: { label: 'Spread', icon: <BookOpen  className="w-4 h-4" />, next: 'single' },
    single: { label: 'Single', icon: <FileText  className="w-4 h-4" />, next: 'auto'   },
};

export function ReaderHeader({
    selectedPdf,
    direction,
    spreadMode,
    pageNumber,
    numPages,
    isEditMode,
    selectedPagesCount,
    showHeader,
    isSearchOpen,
    isFullscreen,
    onClose,
    onToggleDirection,
    onCycleSpreadMode,
    onToggleEditMode,
    onDeletePages,
    onMouseLeave,
    onToggleSearch,
    onToggleFullscreen,
    onOpenHelp,
}: ReaderHeaderProps) {
    return (
        <div
            className={`fixed top-0 left-0 right-0 h-14 border-b border-gray-200 dark:border-gray-700 bg-white/90 dark:bg-gray-900/90 backdrop-blur-sm flex items-center px-4 justify-between shrink-0 z-header transition-transform duration-300 ${
                !showHeader ? '-translate-y-full' : 'translate-y-0'
            }`}
            onMouseLeave={onMouseLeave}
        >
            <div className="flex items-center gap-4">
                <button
                    onClick={onClose}
                    className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-full"
                >
                    <ArrowLeft className="w-5 h-5 text-gray-700 dark:text-gray-300" />
                </button>
                <h1 className="font-semibold truncate max-w-xl text-gray-900 dark:text-gray-100">{selectedPdf}</h1>
            </div>

            <div className="flex items-center gap-2">
                <button
                    onClick={onToggleDirection}
                    className="px-3 py-1.5 text-sm font-medium bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-md transition-colors"
                >
                    {direction === 'rtl' ? 'Right Binding (RTL)' : 'Left Binding (LTR)'}
                </button>
                {/* 見開きモードトグル（Auto / Spread / Single を循環） */}
                <button
                    onClick={onCycleSpreadMode}
                    title={`次のモード: ${SPREAD_MODE_CONFIG[spreadMode].next}`}
                    className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors flex items-center gap-1.5 ${
                        spreadMode === 'auto'
                            ? 'bg-indigo-100 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-300'
                            : 'bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300'
                    }`}
                >
                    {SPREAD_MODE_CONFIG[spreadMode].icon}
                    {SPREAD_MODE_CONFIG[spreadMode].label}
                </button>

                <span className="text-sm tabular-nums text-gray-500 dark:text-gray-400">
                    {pageNumber} / {numPages}
                </span>

                <div className="h-6 w-px bg-gray-300 dark:bg-gray-600 mx-2" />

                {/* 検索ボタン */}
                <button
                    onClick={onToggleSearch}
                    className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors flex items-center gap-2 ${
                        isSearchOpen
                            ? 'bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-400'
                            : 'bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300'
                    }`}
                    title="テキスト検索 (Ctrl+F)"
                >
                    <Search className="w-4 h-4" />
                    Search
                </button>

                {/* フルスクリーン切替ボタン */}
                <button
                    onClick={onToggleFullscreen}
                    className="px-2 py-1.5 text-sm font-medium rounded-md transition-colors bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300"
                    title={isFullscreen ? 'フルスクリーン解除 (f)' : 'フルスクリーン (f)'}
                >
                    {isFullscreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
                </button>

                {/* ショートカット一覧ボタン */}
                <button
                    onClick={onOpenHelp}
                    className="px-2 py-1.5 text-sm font-medium rounded-md transition-colors bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300"
                    title="ショートカット一覧 (?)"
                >
                    <HelpCircle className="w-4 h-4" />
                </button>

                <button
                    onClick={onToggleEditMode}
                    className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors flex items-center gap-2 ${
                        isEditMode
                            ? 'bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-400'
                            : 'bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300'
                    }`}
                >
                    {isEditMode ? <CheckSquare className="w-4 h-4" /> : <Square className="w-4 h-4" />}
                    {isEditMode ? 'Done' : 'Edit'}
                </button>
                {isEditMode && selectedPagesCount > 0 && (
                    <button
                        onClick={onDeletePages}
                        className="px-3 py-1.5 text-sm font-medium bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-400 hover:bg-red-200 dark:hover:bg-red-900/60 rounded-md transition-colors flex items-center gap-2"
                    >
                        <Trash2 className="w-4 h-4" />
                        Delete ({selectedPagesCount})
                    </button>
                )}
            </div>
        </div>
    );
}
