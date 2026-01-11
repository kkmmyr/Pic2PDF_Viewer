import { FileText, CheckSquare, Square } from 'lucide-react';
import { buildStaticUrl } from '../../config/api';
import type { PdfFile } from '../../types';

interface PdfGridProps {
    pdfs: PdfFile[];
    onPdfClick: (pdfName: string) => void;
    isSelectionMode?: boolean;
    selectedItems?: Set<string>;
    onToggleSelect?: (name: string) => void;
}

/**
 * PDF一覧のグリッド表示コンポーネント
 */
export function PdfGrid({
    pdfs,
    onPdfClick,
    isSelectionMode = false,
    selectedItems = new Set(),
    onToggleSelect
}: PdfGridProps) {
    if (pdfs.length === 0) {
        return (
            <div>
                <h2 className="text-lg font-semibold mb-4 text-gray-700">PDFs</h2>
                <p className="text-gray-500">No PDFs found.</p>
            </div>
        );
    }

    return (
        <div>
            <h2 className="text-lg font-semibold mb-4 text-gray-700">PDFs</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
                {pdfs.map((pdf) => (
                    <div
                        key={pdf.name}
                        className={`bg-white rounded-lg shadow-md overflow-hidden hover:shadow-lg transition-shadow cursor-pointer flex flex-col border-2 ${isSelectionMode && selectedItems.has(pdf.name) ? 'border-blue-500' : 'border-transparent'
                            }`}
                        onClick={() => {
                            if (isSelectionMode && onToggleSelect) {
                                onToggleSelect(pdf.name);
                            } else {
                                onPdfClick(pdf.name);
                            }
                        }}
                    >
                        <div className="aspect-[3/4] bg-gray-100 flex items-center justify-center relative">
                            {isSelectionMode && (
                                <div className="absolute top-2 right-2 z-10 bg-white rounded-full">
                                    {selectedItems.has(pdf.name) ? (
                                        <CheckSquare className="w-6 h-6 text-blue-500 fill-white" />
                                    ) : (
                                        <Square className="w-6 h-6 text-gray-400 fill-white" />
                                    )}
                                </div>
                            )}
                            {pdf.thumbnail ? (
                                <>
                                    <img
                                        src={buildStaticUrl(pdf.thumbnail)}
                                        alt={pdf.name}
                                        className="w-full h-full object-cover"
                                        onError={(e) => {
                                            e.currentTarget.style.display = 'none';
                                            e.currentTarget.nextElementSibling?.classList.remove('hidden');
                                        }}
                                    />
                                    <div className="hidden w-full h-full flex items-center justify-center bg-gray-100">
                                        <FileText className="w-12 h-12 text-gray-400" />
                                    </div>
                                </>
                            ) : (
                                <div className="w-full h-full flex items-center justify-center bg-gray-100">
                                    <FileText className="w-12 h-12 text-gray-400" />
                                </div>
                            )}
                        </div>
                        <div className="p-3 bg-white flex-1 flex flex-col justify-between">
                            <span className="font-medium text-sm text-gray-800 line-clamp-2" title={pdf.name}>
                                {pdf.name.replace('.pdf', '')}
                            </span>
                            <div className="mt-2 text-xs text-gray-500">
                                Create: {new Date(pdf.created_at * 1000).toLocaleDateString()}
                            </div>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}
