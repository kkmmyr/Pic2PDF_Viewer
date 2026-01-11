import { ArrowLeft } from 'lucide-react';
import { LibrarySource } from '../../types';

interface LibraryHeaderProps {
    currentPath: string;
    currentSource: LibrarySource;
    isSelectionMode: boolean;
    selectedCount: number;
    onUpClick: () => void;
    onSourceChange: (source: LibrarySource) => void;
    onToggleSelectionMode: () => void;
    onCreateFolder: () => void;
    onMoveSelected: () => void;
}

/**
 * ライブラリビューのヘッダーコンポーネント
 */
export function LibraryHeader({
    currentPath,
    currentSource,
    isSelectionMode,
    selectedCount,
    onUpClick,
    onSourceChange,
    onToggleSelectionMode,
    onCreateFolder,
    onMoveSelected
}: LibraryHeaderProps) {
    return (
        <div className="sticky top-0 h-14 border-b bg-white/90 backdrop-blur-sm flex items-center px-4 justify-between shrink-0 z-50">
            <div className="flex items-center gap-4">
                {currentPath && (
                    <button
                        onClick={onUpClick}
                        className="p-2 hover:bg-gray-100 rounded-full"
                    >
                        <ArrowLeft className="w-5 h-5" />
                    </button>
                )}
                <h1 className="font-semibold truncate">
                    {currentPath ? currentPath.split('/').pop() : 'Library'}
                </h1>
            </div>

            <div className="flex items-center gap-3">
                {/* Action Buttons */}
                <div className="flex gap-2 mr-4">
                    {isSelectionMode ? (
                        <>
                            <span className="text-sm font-medium self-center mr-2">
                                {selectedCount} 選択中
                            </span>
                            <button
                                onClick={onMoveSelected}
                                disabled={selectedCount === 0}
                                className="px-3 py-1.5 bg-blue-600 text-white rounded-md text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                移動
                            </button>
                            <button
                                onClick={onToggleSelectionMode}
                                className="px-3 py-1.5 bg-gray-200 text-gray-700 rounded-md text-sm font-medium hover:bg-gray-300"
                            >
                                キャンセル
                            </button>
                        </>
                    ) : (
                        <>
                            <button
                                onClick={onCreateFolder}
                                className="px-3 py-1.5 bg-gray-100 text-gray-700 rounded-md text-sm font-medium hover:bg-gray-200"
                            >
                                + フォルダ作成
                            </button>
                            <button
                                onClick={onToggleSelectionMode}
                                className="px-3 py-1.5 bg-gray-100 text-gray-700 rounded-md text-sm font-medium hover:bg-gray-200"
                            >
                                選択
                            </button>
                        </>
                    )}
                </div>

                {/* Source Tabs */}
                <div className="flex bg-gray-100 rounded-lg p-1">
                    <button
                        onClick={() => onSourceChange('generated')}
                        className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${currentSource === 'generated'
                            ? 'bg-white text-blue-600 shadow-sm'
                            : 'text-gray-500 hover:text-gray-900'
                            }`}
                    >
                        Main
                    </button>
                    <button
                        onClick={() => onSourceChange('kindle')}
                        className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${currentSource === 'kindle'
                            ? 'bg-white text-blue-600 shadow-sm'
                            : 'text-gray-500 hover:text-gray-900'
                            }`}
                    >
                        Kindle
                    </button>
                </div>
            </div>
        </div>
    );
}
