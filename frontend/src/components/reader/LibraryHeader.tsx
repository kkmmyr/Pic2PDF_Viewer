import { ArrowLeft } from 'lucide-react';
import { LibrarySource } from '../../types';

interface LibraryHeaderProps {
    currentPath: string;
    currentSource: LibrarySource;
    onUpClick: () => void;
    onSourceChange: (source: LibrarySource) => void;
}

/**
 * ライブラリビューのヘッダーコンポーネント
 */
export function LibraryHeader({ currentPath, currentSource, onUpClick, onSourceChange }: LibraryHeaderProps) {
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
    );
}
