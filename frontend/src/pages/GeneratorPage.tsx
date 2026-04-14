import { useState } from 'react';
import { FolderSearch, Loader2, Zap } from 'lucide-react';
import { API_ENDPOINTS } from '../config/api';
import apiClient from '../config/api_client';
import { usePdfStatus } from '../hooks/usePdfStatus';
import type { GenerateResponse, StatusItem } from '../types';

const DEFAULT_SOURCE_DIR = import.meta.env.VITE_DEFAULT_SOURCE_DIR || '';
const DEFAULT_QUALITY = 50;

export default function GeneratorPage() {
    const [sourceDir, setSourceDir] = useState(DEFAULT_SOURCE_DIR);
    // 生成・圧縮を別々のローディング状態で管理し、どちらの処理中か明確にする
    const [isGenerating, setIsGenerating] = useState(false);
    const [isCompressing, setIsCompressing] = useState(false);
    const [result, setResult] = useState<GenerateResponse | null>(null);
    const [error, setError] = useState<string | null>(null);

    const [generateCompressed, setGenerateCompressed] = useState(true);
    const [quality, setQuality] = useState(DEFAULT_QUALITY);

    const isLoading = isGenerating || isCompressing;
    const { statusItems, refetch: fetchStatus } = usePdfStatus(sourceDir, isLoading);

    const handleGenerate = async () => {
        if (!sourceDir) return;

        setIsGenerating(true);
        setError(null);
        setResult(null);

        try {
            const data = await apiClient.post<unknown, GenerateResponse>(API_ENDPOINTS.GENERATE, {
                source_dir: sourceDir,
                generate_compressed: generateCompressed,
                quality,
            });
            setResult(data);
            fetchStatus();
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : '生成に失敗しました。');
        } finally {
            setIsGenerating(false);
        }
    };

    const handleBatchCompress = async () => {
        setIsCompressing(true);
        setError(null);
        setResult(null);

        try {
            const data = await apiClient.post<unknown, GenerateResponse>(API_ENDPOINTS.BATCH_COMPRESS, {
                quality,
            });
            setResult(data);
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : '一括圧縮に失敗しました。');
        } finally {
            setIsCompressing(false);
        }
    };

    const getStatusBadgeClass = (status: StatusItem['status']) => {
        switch (status) {
            case 'completed':   return 'bg-green-100 text-green-800';
            case 'in_progress': return 'bg-blue-100 text-blue-800';
            default:            return 'bg-gray-100 text-gray-800';
        }
    };

    const getStatusLabel = (status: StatusItem['status']) => {
        switch (status) {
            case 'completed':   return 'Completed';
            case 'in_progress': return 'In Progress';
            default:            return 'Not Started';
        }
    };

    return (
        <div className="max-w-4xl mx-auto p-6">
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-8">
                <h2 className="text-2xl font-bold text-gray-800 mb-6 flex items-center gap-2">
                    <FolderSearch className="text-blue-600" />
                    PDF Generator
                </h2>

                <div className="space-y-6">
                    {/* Source Directory Input */}
                    <div>
                        <label htmlFor="sourceDir" className="block text-sm font-medium text-gray-700 mb-1">
                            Source Directory Path
                        </label>
                        <div className="flex gap-2">
                            <input
                                type="text"
                                id="sourceDir"
                                value={sourceDir}
                                onChange={(e) => setSourceDir(e.target.value)}
                                placeholder="C:\Path\To\Images"
                                className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                            />
                            <button
                                onClick={fetchStatus}
                                className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 border border-gray-300 transition-colors"
                            >
                                Check Status
                            </button>
                        </div>
                        <p className="text-sm text-gray-500 mt-1">
                            Enter the absolute path to the folder containing your WebP images.
                        </p>
                    </div>

                    {/* Compression Options */}
                    <div className="p-4 bg-blue-50 rounded-lg border border-blue-100 space-y-4">
                        <div className="flex items-center gap-3">
                            <input
                                type="checkbox"
                                id="generateCompressed"
                                checked={generateCompressed}
                                onChange={(e) => setGenerateCompressed(e.target.checked)}
                                className="w-5 h-5 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                            />
                            <label htmlFor="generateCompressed" className="text-sm font-semibold text-gray-800 flex items-center gap-2 cursor-pointer">
                                <Zap size={16} className="text-amber-500 fill-amber-500" />
                                Generate Compressed Version (別途保存)
                            </label>
                        </div>

                        {generateCompressed && (
                            <div className="pl-8 space-y-2">
                                <div className="flex justify-between text-sm text-gray-600">
                                    <span>Compression Quality: {quality}</span>
                                    <span className="text-xs">Lower is smaller but lower quality</span>
                                </div>
                                <input
                                    type="range"
                                    min="10"
                                    max="95"
                                    step="5"
                                    value={quality}
                                    onChange={(e) => setQuality(parseInt(e.target.value))}
                                    className="w-full h-2 bg-blue-200 rounded-lg appearance-none cursor-pointer accent-blue-600"
                                />
                            </div>
                        )}
                    </div>

                    {/* Buttons */}
                    <div className="flex flex-col gap-4">
                        <button
                            onClick={handleGenerate}
                            disabled={isLoading || !sourceDir}
                            className="w-full flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-300 text-white font-bold py-4 rounded-xl shadow-lg shadow-blue-200 transition-all hover:scale-[1.01] active:scale-[0.99]"
                        >
                            {isGenerating ? (
                                <>
                                    <Loader2 className="animate-spin" />
                                    Generating...
                                </>
                            ) : (
                                <>
                                    <FolderSearch size={22} />
                                    Scan & Generate
                                </>
                            )}
                        </button>

                        <div className="relative">
                            <div className="absolute inset-0 flex items-center">
                                <span className="w-full border-t border-gray-200" />
                            </div>
                            <div className="relative flex justify-center text-xs uppercase">
                                <span className="bg-white px-2 text-gray-500">Or manage existing</span>
                            </div>
                        </div>

                        <button
                            onClick={handleBatchCompress}
                            disabled={isLoading}
                            className="w-full flex items-center justify-center gap-2 bg-white hover:bg-gray-50 disabled:bg-gray-50 text-gray-700 font-semibold py-3 rounded-xl border border-gray-300 transition-all"
                        >
                            {isCompressing ? (
                                <Loader2 className="animate-spin" size={18} />
                            ) : (
                                <Zap size={18} className="text-amber-500" />
                            )}
                            {isCompressing ? 'Compressing...' : 'Batch Compress All Existing PDFs'}
                        </button>
                    </div>

                    {/* Error Message */}
                    {error && (
                        <div className="p-4 bg-red-50 text-red-700 rounded-lg border border-red-200 animate-in fade-in slide-in-from-top-2">
                            Error: {error}
                        </div>
                    )}

                    {/* Status Table */}
                    {statusItems.length > 0 && (
                        <div className="mt-8">
                            <h3 className="text-lg font-semibold text-gray-800 mb-4">Items Status</h3>
                            <div className="overflow-x-auto border border-gray-200 rounded-lg shadow-sm">
                                <table className="w-full text-left text-sm">
                                    <thead className="bg-gray-50 text-gray-600 font-medium border-b border-gray-200">
                                        <tr>
                                            <th className="px-4 py-3">Name</th>
                                            <th className="px-4 py-3">Type</th>
                                            <th className="px-4 py-3">Status</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-gray-200">
                                        {statusItems.map((item) => (
                                            <tr key={item.name} className="hover:bg-gray-50 transition-colors">
                                                <td className="px-4 py-3 font-medium text-gray-900">{item.name}</td>
                                                <td className="px-4 py-3 text-gray-500 uppercase text-[10px] tracking-wider font-semibold">{item.type}</td>
                                                <td className="px-4 py-3">
                                                    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${getStatusBadgeClass(item.status)}`}>
                                                        {getStatusLabel(item.status)}
                                                    </span>
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    )}

                    {/* Result Message */}
                    {result && (
                        <div className="p-4 bg-green-50 text-green-700 rounded-lg border border-green-200 animate-in fade-in zoom-in-95">
                            <p className="font-bold mb-2">{result.message}</p>
                            <ul className="list-disc list-inside text-sm space-y-1">
                                {result.files.map((file) => (
                                    <li key={file} className="font-medium">{file}</li>
                                ))}
                            </ul>
                            {generateCompressed && (
                                <p className="mt-3 text-xs text-green-600 italic">
                                    * 圧縮版は `pdfs_compressed` フォルダに保存されました。
                                </p>
                            )}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
