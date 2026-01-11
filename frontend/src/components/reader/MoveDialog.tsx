import { useState, useEffect } from 'react';
import { Folder, ArrowLeft } from 'lucide-react';
import { buildApiUrl, API_ENDPOINTS } from '../../config/api';
import { LibrarySource } from '../../types';

interface MoveDialogProps {
    open: boolean;
    onClose: () => void;
    onMove: (destination: string) => void;
    currentSource: LibrarySource;
    sourcePath: string; // The path where we are moving FROM (to prevent moving into itself if needed, or to show relative ?)
    // Actually sourcePath is where the ITEMS are properly located.
    // destination is selected here.
}

interface DirectoryItem {
    name: string;
    path: string; // Relative path from root
}

export function MoveDialog({ open, onClose, onMove, currentSource }: MoveDialogProps) {
    const [currentPath, setCurrentPath] = useState("");
    const [directories, setDirectories] = useState<DirectoryItem[]>([]);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (open) {
            setCurrentPath(""); // Reset to root on open
            fetchDirectories("");
        }
    }, [open, currentSource]);

    const fetchDirectories = async (path: string) => {
        setLoading(true);
        try {
            const params = new URLSearchParams();
            if (path) params.append("path", path);
            params.append("source", currentSource);

            // Using existing PDFS endpoint to get directories
            // Since API_ENDPOINTS.PDFS returns directories in the response
            const res = await fetch(buildApiUrl(`${API_ENDPOINTS.PDFS}?${params.toString()}`));
            const data = await res.json();

            // Map strings to objects
            if (data.directories) {
                const dirs = data.directories.map((d: string) => ({
                    name: d,
                    path: path ? `${path}/${d}` : d
                }));
                setDirectories(dirs);
            } else {
                setDirectories([]);
            }
        } catch (e) {
            console.error("Failed to fetch directories", e);
        } finally {
            setLoading(false);
        }
    };

    const handleNavigate = (dirName: string) => {
        const newPath = currentPath ? `${currentPath}/${dirName}` : dirName;
        setCurrentPath(newPath);
        fetchDirectories(newPath);
    };

    const handleUp = () => {
        if (!currentPath) return;
        const parts = currentPath.split('/');
        parts.pop();
        const newPath = parts.join('/');
        setCurrentPath(newPath);
        fetchDirectories(newPath);
    };

    if (!open) return null;

    return (
        <div className="fixed inset-0 bg-black/50 z-[100] flex items-center justify-center">
            <div className="bg-white rounded-lg shadow-xl w-full max-w-md flex flex-col max-h-[80vh]">
                <div className="p-4 border-b flex justify-between items-center">
                    <h2 className="font-semibold text-lg">移動先を選択</h2>
                    <button onClick={onClose} className="text-gray-500 hover:text-gray-700">✕</button>
                </div>

                <div className="p-2 border-b bg-gray-50 flex items-center gap-2">
                    <button
                        onClick={handleUp}
                        disabled={!currentPath}
                        className="p-1 hover:bg-gray-200 rounded disabled:opacity-30"
                    >
                        <ArrowLeft className="w-4 h-4" />
                    </button>
                    <div className="text-sm font-mono truncate flex-1">
                        /{currentPath}
                    </div>
                </div>

                <div className="flex-1 overflow-y-auto p-2 min-h-[300px]">
                    {loading ? (
                        <div className="flex justify-center p-4">Loading...</div>
                    ) : (
                        <div className="space-y-1">
                            {/* Current Folder Selection Option */}
                            <button
                                onClick={() => onMove(currentPath)}
                                className="w-full text-left px-3 py-2 hover:bg-blue-50 text-blue-600 rounded flex items-center gap-2 font-medium"
                            >
                                <span className="text-xs border border-blue-600 rounded px-1">現在地</span>
                                ここに移動 (/{currentPath})
                            </button>

                            <hr className="my-2" />

                            {directories.map((dir) => (
                                <button
                                    key={dir.name}
                                    onClick={() => handleNavigate(dir.name)}
                                    className="w-full text-left px-3 py-2 hover:bg-gray-100 rounded flex items-center gap-2"
                                >
                                    <Folder className="w-4 h-4 text-yellow-500 fill-yellow-500" />
                                    {dir.name}
                                </button>
                            ))}
                            {directories.length === 0 && (
                                <div className="text-gray-400 text-sm text-center py-4">サブフォルダはありません</div>
                            )}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
