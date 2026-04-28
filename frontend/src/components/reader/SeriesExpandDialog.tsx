import { Library } from 'lucide-react';
import { Dialog, DialogBody } from '../ui/Dialog';
import { LazyThumbnail } from './LazyThumbnail';
import type { PdfFile } from '../../types';

interface SeriesExpandDialogProps {
    open: boolean;
    seriesTitle: string;
    members: PdfFile[];
    /** 各メンバーの巻数を name から引く（小数巻あり） */
    getIndex: (name: string) => number;
    onClose: () => void;
    onPdfClick: (name: string) => void;
}

/** 巻数を表示用文字列に整形する（整数は整数のまま、小数は小数点を表示）。 */
function formatVolumeIndex(n: number): string {
    if (n <= 0) return '';
    return Number.isInteger(n) ? String(n) : String(n);  // n.toString() は 2.5 → "2.5"
}

/**
 * シリーズ展開ダイアログ。代表書籍をクリックしたときに開き、
 * 同シリーズの全巻を巻数順に並べる。クリックで対象 PDF を開く。
 */
export function SeriesExpandDialog({
    open, seriesTitle, members, getIndex, onClose, onPdfClick,
}: SeriesExpandDialogProps) {
    const subtitle = `${members.length} 巻`;

    return (
        <Dialog
            open={open}
            title={seriesTitle ? `📚 ${seriesTitle}` : '📚 シリーズ'}
            subtitle={subtitle}
            onClose={onClose}
            maxWidth="md"
        >
            <DialogBody>
                <div className="grid grid-cols-3 gap-3 max-h-[60vh] overflow-y-auto">
                    {members.map((m) => {
                        const idx = getIndex(m.name);
                        return (
                            <button
                                key={m.name}
                                onClick={() => { onClose(); onPdfClick(m.name); }}
                                className="text-left rounded-lg overflow-hidden border border-gray-200 dark:border-gray-700 hover:border-purple-400 dark:hover:border-purple-600 transition-colors bg-white dark:bg-gray-800"
                            >
                                <div className="aspect-[3/4] relative">
                                    <LazyThumbnail src={m.thumbnail} alt={m.name} className="absolute inset-0" />
                                    {idx > 0 && (
                                        <div className="absolute top-2 left-2 px-1.5 py-0.5 rounded bg-purple-600 text-white text-xs font-semibold flex items-center gap-1 shadow">
                                            <Library className="w-3 h-3" />
                                            {formatVolumeIndex(idx)}
                                        </div>
                                    )}
                                </div>
                                <div className="p-2">
                                    <span className="text-xs text-gray-800 dark:text-gray-200 line-clamp-2" title={m.name}>
                                        {m.name.replace(/\.pdf$/i, '')}
                                    </span>
                                </div>
                            </button>
                        );
                    })}
                </div>
            </DialogBody>
        </Dialog>
    );
}
