import { Folder } from 'lucide-react';

interface FolderGridProps {
    directories: string[];
    onFolderClick: (dirName: string) => void;
}

/**
 * フォルダ一覧のグリッド表示コンポーネント
 */
export function FolderGrid({ directories, onFolderClick }: FolderGridProps) {
    if (directories.length === 0) return null;

    return (
        <div className="mb-8">
            <h2 className="text-lg font-semibold mb-4 text-gray-700">Folders</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
                {directories.map((dir) => (
                    <div
                        key={dir}
                        onClick={() => onFolderClick(dir)}
                        className="group cursor-pointer bg-white p-4 rounded-xl shadow-sm hover:shadow-md transition-all border border-gray-100"
                    >
                        <div className="aspect-[4/3] bg-blue-50 rounded-lg mb-3 flex items-center justify-center group-hover:bg-blue-100 transition-colors">
                            <Folder className="w-12 h-12 text-blue-400" />
                        </div>
                        <p className="font-medium text-gray-700 truncate text-sm">{dir}</p>
                    </div>
                ))}
            </div>
        </div>
    );
}
