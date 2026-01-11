import { FileText } from 'lucide-react';
import { buildStaticUrl } from '../../config/api';
import type { PdfFile } from '../../types';

interface PdfGridProps {
    pdfs: PdfFile[];
    onPdfClick: (pdfName: string) => void;
}

/**
 * PDF一覧のグリッド表示コンポーネント
 */
export function PdfGrid({ pdfs, onPdfClick }: PdfGridProps) {
    return (
        <div>
            <h2 className="text-lg font-semibold mb-4 text-gray-700">PDFs</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
                {pdfs.map((pdf) => (
                    <div
                        key={pdf.name}
                        onClick={() => onPdfClick(pdf.name)}
                        className="group cursor-pointer bg-white p-4 rounded-xl shadow-sm hover:shadow-md transition-all border border-gray-100"
                    >
                        <div className="aspect-[3/4] bg-gray-50 rounded-lg mb-3 overflow-hidden relative border border-gray-100">
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
                        <p className="font-medium text-gray-700 truncate text-sm" title={pdf.name}>
                            {pdf.name}
                        </p>
                    </div>
                ))}
            </div>
        </div>
    );
}
