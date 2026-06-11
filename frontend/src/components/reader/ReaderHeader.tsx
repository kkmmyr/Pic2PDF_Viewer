import {
    ArrowLeft,
    CheckSquare,
    Square,
    Search,
    Wand2,
    BookOpen,
    FileText,
    Maximize2,
    Minimize2,
    HelpCircle,
} from 'lucide-react';
import type { SpreadMode } from '@/types';
import { useReaderContext } from '@/contexts/ReaderContext';

const SPREAD_MODE_CONFIG: Record<
    SpreadMode,
    { label: string; icon: React.ReactNode; next: SpreadMode }
> = {
    auto: { label: 'Auto', icon: <Wand2 className="w-4 h-4" />, next: 'spread' },
    spread: { label: 'Spread', icon: <BookOpen className="w-4 h-4" />, next: 'single' },
    single: { label: 'Single', icon: <FileText className="w-4 h-4" />, next: 'auto' },
};

export function ReaderHeader() {
    const {
        selectedPdf,
        direction,
        spreadMode,
        pageNumber,
        numPages,
        isEditMode,
        showHeader,
        isSearchOpen,
        isFullscreen,
        isOnRelatedPage,
        handleClose,
        toggleDirection,
        cycleSpreadMode,
        toggleEditMode,
        toggleSearch,
        toggleFullscreen,
        openHelp,
    } = useReaderContext();

    return (
        <div
            className={`fixed top-0 left-0 right-0 border-b border-gray-200 dark:border-gray-700 bg-white/90 dark:bg-gray-900/90 backdrop-blur-sm shrink-0 z-header transition-transform duration-300 ${
                !showHeader ? '-translate-y-full' : 'translate-y-0'
            }`}
            style={{ paddingTop: 'env(safe-area-inset-top, 0px)' }}
        >
            <div className="h-16 flex items-center px-4 justify-between">
                <div className="flex items-center gap-4">
                    <button
                        onClick={handleClose}
                        className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-full"
                    >
                        <ArrowLeft className="w-5 h-5 text-gray-700 dark:text-gray-300" />
                    </button>
                    <h1 className="font-semibold truncate max-w-xl text-gray-900 dark:text-gray-100">
                        {selectedPdf}
                    </h1>
                </div>

                <div className="flex items-center gap-2">
                    <button
                        onClick={toggleDirection}
                        className="px-3 py-1.5 text-sm font-medium bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-md transition-colors"
                    >
                        {direction === 'rtl' ? 'Right Binding (RTL)' : 'Left Binding (LTR)'}
                    </button>
                    <button
                        onClick={cycleSpreadMode}
                        title={`次のモード: ${SPREAD_MODE_CONFIG[spreadMode].next}`}
                        className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors flex items-center gap-1.5 ${
                            spreadMode === 'auto'
                                ? 'bg-accent-100 dark:bg-accent-900/40 text-accent-700 dark:text-accent-300'
                                : 'bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300'
                        }`}
                    >
                        {SPREAD_MODE_CONFIG[spreadMode].icon}
                        {SPREAD_MODE_CONFIG[spreadMode].label}
                    </button>

                    {!isOnRelatedPage && (
                        <span className="text-sm tabular-nums text-gray-500 dark:text-gray-400">
                            {pageNumber} / {numPages}
                        </span>
                    )}

                    <div className="h-6 w-px bg-gray-300 dark:bg-gray-600 mx-2" />

                    <button
                        onClick={toggleSearch}
                        className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors flex items-center gap-2 ${
                            isSearchOpen
                                ? 'bg-accent-100 dark:bg-accent-900/40 text-accent-700 dark:text-accent-300'
                                : 'bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300'
                        }`}
                        title="テキスト検索 (Ctrl+F)"
                    >
                        <Search className="w-4 h-4" />
                        Search
                    </button>

                    <button
                        onClick={toggleFullscreen}
                        className="px-2 py-1.5 text-sm font-medium rounded-md transition-colors bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300"
                        title={isFullscreen ? 'フルスクリーン解除 (f)' : 'フルスクリーン (f)'}
                    >
                        {isFullscreen ? (
                            <Minimize2 className="w-4 h-4" />
                        ) : (
                            <Maximize2 className="w-4 h-4" />
                        )}
                    </button>

                    <button
                        onClick={openHelp}
                        className="px-2 py-1.5 text-sm font-medium rounded-md transition-colors bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300"
                        title="ショートカット一覧 (?)"
                    >
                        <HelpCircle className="w-4 h-4" />
                    </button>

                    <button
                        onClick={toggleEditMode}
                        title="編集モード (e) — ページ削除グリッドを開く"
                        className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors flex items-center gap-2 ${
                            isEditMode
                                ? 'bg-accent-100 dark:bg-accent-900/40 text-accent-700 dark:text-accent-300'
                                : 'bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300'
                        }`}
                    >
                        {isEditMode ? (
                            <CheckSquare className="w-4 h-4" />
                        ) : (
                            <Square className="w-4 h-4" />
                        )}
                        {isEditMode ? 'Done' : 'Edit'}
                    </button>
                </div>
            </div>
        </div>
    );
}
