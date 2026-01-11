import { ArrowLeft } from 'lucide-react';

interface LibraryHeaderProps {
    currentPath: string;
    onUpClick: () => void;
}

/**
 * ライブラリビューのヘッダーコンポーネント
 */
export function LibraryHeader({ currentPath, onUpClick }: LibraryHeaderProps) {
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
        </div>
    );
}
