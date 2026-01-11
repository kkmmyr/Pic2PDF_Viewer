import { ArrowLeft, Trash2, CheckSquare, Square } from 'lucide-react';
import type { ReadingDirection } from '../../types';

interface ReaderHeaderProps {
    selectedPdf: string;
    direction: ReadingDirection;
    isSpread: boolean;
    pageNumber: number;
    numPages: number;
    isEditMode: boolean;
    selectedPagesCount: number;
    showHeader: boolean;
    onClose: () => void;
    onToggleDirection: () => void;
    onToggleSpread: () => void;
    onToggleEditMode: () => void;
    onDeletePages: () => void;
    onMouseLeave: () => void;
}

/**
 * リーダービューのヘッダーコンポーネント
 */
export function ReaderHeader({
    selectedPdf,
    direction,
    isSpread,
    pageNumber,
    numPages,
    isEditMode,
    selectedPagesCount,
    showHeader,
    onClose,
    onToggleDirection,
    onToggleSpread,
    onToggleEditMode,
    onDeletePages,
    onMouseLeave,
}: ReaderHeaderProps) {
    return (
        <div
            className={`fixed top-0 left-0 right-0 h-14 border-b bg-white/90 backdrop-blur-sm flex items-center px-4 justify-between shrink-0 z-50 transition-transform duration-300 ${!showHeader ? '-translate-y-full' : 'translate-y-0'
                }`}
            onMouseLeave={onMouseLeave}
        >
            <div className="flex items-center gap-4">
                <button
                    onClick={onClose}
                    className="p-2 hover:bg-gray-100 rounded-full"
                >
                    <ArrowLeft className="w-5 h-5" />
                </button>
                <h1 className="font-semibold truncate max-w-xl">{selectedPdf}</h1>
            </div>

            <div className="flex items-center gap-2">
                <button
                    onClick={onToggleDirection}
                    className="px-3 py-1.5 text-sm font-medium bg-gray-100 hover:bg-gray-200 rounded-md transition-colors"
                >
                    {direction === 'rtl' ? 'Right Binding (RTL)' : 'Left Binding (LTR)'}
                </button>
                <button
                    onClick={onToggleSpread}
                    className="px-3 py-1.5 text-sm font-medium bg-gray-100 hover:bg-gray-200 rounded-md transition-colors"
                >
                    {isSpread ? 'Spread' : 'Single'}
                </button>
                <span className="text-sm text-gray-500">
                    {pageNumber} / {numPages}
                </span>
                <div className="h-6 w-px bg-gray-300 mx-2" />
                <button
                    onClick={onToggleEditMode}
                    className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors flex items-center gap-2 ${isEditMode ? 'bg-blue-100 text-blue-700' : 'bg-gray-100 hover:bg-gray-200'
                        }`}
                >
                    {isEditMode ? <CheckSquare className="w-4 h-4" /> : <Square className="w-4 h-4" />}
                    {isEditMode ? 'Done' : 'Edit'}
                </button>
                {isEditMode && selectedPagesCount > 0 && (
                    <button
                        onClick={onDeletePages}
                        className="px-3 py-1.5 text-sm font-medium bg-red-100 text-red-700 hover:bg-red-200 rounded-md transition-colors flex items-center gap-2"
                    >
                        <Trash2 className="w-4 h-4" />
                        Delete ({selectedPagesCount})
                    </button>
                )}
            </div>
        </div>
    );
}
