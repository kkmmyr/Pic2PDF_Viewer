import { useState, useEffect, useCallback } from 'react';
import { FolderSearch, Loader2 } from 'lucide-react';
import { buildApiUrl, API_ENDPOINTS } from '../config/api';
import type { StatusItem, GenerateResponse } from '../types';

// デフォルトの入力ディレクトリパス
const DEFAULT_SOURCE_DIR = 'F:\\61.tool\\Pic2PDF_Viewer\\backend\\input';

export default function GeneratorPage() {
    const [sourceDir, setSourceDir] = useState(DEFAULT_SOURCE_DIR);
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState<GenerateResponse | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [statusItems, setStatusItems] = useState<StatusItem[]>([]);

    const fetchStatus = useCallback(async () => {
        if (!sourceDir) return;
        try {
            const params = new URLSearchParams({ source_dir: sourceDir });
            const res = await fetch(buildApiUrl(`${API_ENDPOINTS.STATUS}?${params.toString()}`));
            const data = await res.json();
            setStatusItems(data.items || []);
        } catch (e) {
            console.error("Failed to fetch status", e);
        }
    }, [sourceDir]);

    // Poll status while loading
    useEffect(() => {
        let interval: ReturnType<typeof setInterval>;
        if (loading) {
            interval = setInterval(fetchStatus, 1000);
        }
        return () => clearInterval(interval);
    }, [loading, fetchStatus]);

    const handleGenerate = async () => {
        if (!sourceDir) return;

        setLoading(true);
        setError(null);
        setResult(null);

        // Start polling immediately
        fetchStatus();

        try {
            const response = await fetch(buildApiUrl(API_ENDPOINTS.GENERATE), {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ source_dir: sourceDir }),
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Generation failed');
            }

            const data = await response.json();
            setResult(data);
            fetchStatus(); // Final status check
        } catch (err: unknown) {
            const message = err instanceof Error ? err.message : 'Unknown error';
            setError(message);
        } finally {
            setLoading(false);
        }
    };

    const getStatusBadgeClass = (status: StatusItem['status']) => {
        switch (status) {
            case 'completed':
                return 'bg-green-100 text-green-800';
            case 'in_progress':
                return 'bg-blue-100 text-blue-800';
            default:
                return 'bg-gray-100 text-gray-800';
        }
    };

    const getStatusLabel = (status: StatusItem['status']) => {
        switch (status) {
            case 'completed':
                return 'Completed';
            case 'in_progress':
                return 'In Progress';
            default:
                return 'Not Started';
        }
    };

    return (
        <div className="max-w-4xl mx-auto p-6">
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-8">
                <h2 className="text-2xl font-bold text-gray-800 mb-6">PDF Generator</h2>

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
                                className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 border border-gray-300"
                            >
                                Check Status
                            </button>
                        </div>
                        <p className="text-sm text-gray-500 mt-1">
                            Enter the absolute path to the folder containing your WebP images.
                        </p>
                    </div>

                    {/* Generate Button */}
                    <button
                        onClick={handleGenerate}
                        disabled={loading || !sourceDir}
                        className="w-full flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-300 text-white font-medium py-3 rounded-lg transition-colors"
                    >
                        {loading ? (
                            <>
                                <Loader2 className="animate-spin" />
                                Processing...
                            </>
                        ) : (
                            <>
                                <FolderSearch size={20} />
                                Scan & Generate
                            </>
                        )}
                    </button>

                    {/* Error Message */}
                    {error && (
                        <div className="p-4 bg-red-50 text-red-700 rounded-lg border border-red-200">
                            Error: {error}
                        </div>
                    )}

                    {/* Status Table */}
                    {statusItems.length > 0 && (
                        <div className="mt-8">
                            <h3 className="text-lg font-semibold text-gray-800 mb-4">Items Status</h3>
                            <div className="overflow-x-auto border border-gray-200 rounded-lg">
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
                                            <tr key={item.name} className="hover:bg-gray-50">
                                                <td className="px-4 py-3 font-medium text-gray-900">{item.name}</td>
                                                <td className="px-4 py-3 text-gray-500 uppercase text-xs">{item.type}</td>
                                                <td className="px-4 py-3">
                                                    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getStatusBadgeClass(item.status)}`}>
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
                        <div className="p-4 bg-green-50 text-green-700 rounded-lg border border-green-200">
                            <p className="font-medium mb-2">{result.message}</p>
                            <ul className="list-disc list-inside text-sm space-y-1">
                                {result.files.map((file) => (
                                    <li key={file}>{file}</li>
                                ))}
                            </ul>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
