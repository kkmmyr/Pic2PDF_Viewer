import { useState, useEffect } from 'react';
import { Folder, ArrowLeft } from 'lucide-react';
import { API_ENDPOINTS } from '../../config/api';
import apiClient from '../../config/api_client';
import type { LibrarySource, PdfListResponse } from '../../types';
import { Dialog } from '../ui/Dialog';

interface MoveDialogProps {
    open: boolean;
    onClose: () => void;
    onMove: (destination: string) => void;
    currentSource: LibrarySource;
    sourcePath: string;
}

interface DirectoryItem {
    name: string;
    path: string;
}

export function MoveDialog({ open, onClose, onMove, currentSource }: MoveDialogProps) {
    const [currentPath, setCurrentPath] = useState("");
    const [directories, setDirectories] = useState<DirectoryItem[]>([]);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (open) {
            setCurrentPath("");
            fetchDirectories("");
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [open, currentSource]);

    const fetchDirectories = async (path: string) => {
        setLoading(true);
        try {
            const data = await apiClient.get<unknown, PdfListResponse>(
                API_ENDPOINTS.PDFS,
                { params: { path, source: currentSource } }
            );
            const dirs = (data.directories ?? []).map((d) => ({
                name: d,
                path: path ? `${path}/${d}` : d,
            }));
            setDirectories(dirs);
        } catch (e) {
            console.error("Failed to fetch directories", e);
            setDirectories([]);
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

    return (
        <Dialog open={open} title="移動先を選択" onClose={onClose} maxWidth="md">
            <div className="p-2 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 flex items-center gap-2">
                <button
                    onClick={handleUp}
                    disabled={!currentPath}
                    className="p-1 hover:bg-gray-200 dark:hover:bg-gray-700 rounded disabled:opacity-30 text-gray-700 dark:text-gray-300"
                >
                    <ArrowLeft className="w-4 h-4" />
                </button>
                <div className="text-sm font-mono truncate flex-1 text-gray-700 dark:text-gray-300">
                    /{currentPath}
                </div>
            </div>

            <div className="overflow-y-auto p-2 min-h-[300px] max-h-[50vh] bg-white dark:bg-gray-900">
                {loading ? (
                    <div className="flex justify-center p-4 text-gray-500 dark:text-gray-400">Loading...</div>
                ) : (
                    <div className="space-y-1">
                        {/* 現在地に移動するボタン */}
                        <button
                            onClick={() => onMove(currentPath)}
                            className="w-full text-left px-3 py-2 hover:bg-blue-50 dark:hover:bg-blue-900/30 text-blue-600 dark:text-blue-400 rounded flex items-center gap-2 font-medium"
                        >
                            <span className="text-xs border border-blue-600 dark:border-blue-400 rounded px-1">現在地</span>
                            ここに移動 (/{currentPath})
                        </button>

                        <hr className="my-2 border-gray-200 dark:border-gray-700" />

                        {directories.map((dir) => (
                            <button
                                key={dir.name}
                                onClick={() => handleNavigate(dir.name)}
                                className="w-full text-left px-3 py-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded flex items-center gap-2 text-gray-800 dark:text-gray-200"
                            >
                                <Folder className="w-4 h-4 text-yellow-500 fill-yellow-500" />
                                {dir.name}
                            </button>
                        ))}
                        {directories.length === 0 && (
                            <div className="text-gray-400 dark:text-gray-500 text-sm text-center py-4">サブフォルダはありません</div>
                        )}
                    </div>
                )}
            </div>
        </Dialog>
    );
}
