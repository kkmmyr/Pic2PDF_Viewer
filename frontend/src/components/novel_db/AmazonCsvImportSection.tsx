/**
 * Amazon デジタル購入履歴 CSV のインポート UI（4.3）。
 * LibrarySection ヘッダーに配置。CSV 選択 → プレビュー → 保存フロー。
 */
import { useRef, useState } from 'react';
import { Upload } from 'lucide-react';

import { applyNovelMetaImport, fetchNovelMetaImportPreview } from '../../features/novel_db/api';
import type { BookSummary, MetaImportPreviewRow } from '../../features/novel_db/types';
import { useToast } from '../../hooks/useToast';
import { ToastContainer } from '../reader/ToastContainer';
import {
    Dialog,
    DialogBody,
    DialogCancelButton,
    DialogFooter,
    DialogPrimaryButton,
} from '../ui/Dialog';

interface Props {
    books: BookSummary[];
    onApplied: () => void;
}

export default function AmazonCsvImportSection({ books, onApplied }: Props) {
    const [open, setOpen] = useState(false);
    const [rows, setRows] = useState<MetaImportPreviewRow[]>([]);
    const [overrides, setOverrides] = useState<Record<number, string>>({});
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const inputRef = useRef<HTMLInputElement>(null);
    const { toasts, showToast, dismissToast } = useToast();

    const handleFiles = async (files: FileList | null) => {
        if (!files || files.length === 0) return;
        setLoading(true);
        setError(null);
        try {
            const result = await fetchNovelMetaImportPreview(Array.from(files));
            setRows(result);
            setOverrides({});
            setOpen(true);
        } catch {
            setError('CSV の読み込みに失敗しました。');
        } finally {
            setLoading(false);
        }
    };

    const handleApply = async () => {
        setSaving(true);
        setError(null);
        try {
            const items = rows
                .map((r, i) => {
                    const book = overrides[i] ?? r.matched_book;
                    if (!book) return null;
                    return {
                        book_key: `${book}.pdf`,
                        authors: r.authors,
                        series_id: r.series_id,
                        volume: r.volume ?? undefined,
                        publisher: r.publisher,
                        asin: r.asin,
                    };
                })
                .filter((it): it is NonNullable<typeof it> => it !== null);
            const res = await applyNovelMetaImport(items);
            setOpen(false);
            setRows([]);
            onApplied();
            showToast(`${res.updated_count} 冊のメタデータを更新しました。`, 'success');
        } catch {
            setError('保存に失敗しました。');
        } finally {
            setSaving(false);
        }
    };

    return (
        <>
            <button
                onClick={() => inputRef.current?.click()}
                disabled={loading}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50"
            >
                <Upload className="w-3.5 h-3.5" />
                {loading ? '読み込み中...' : 'Amazon CSV インポート'}
            </button>
            <input
                ref={inputRef}
                type="file"
                accept=".csv"
                multiple
                className="hidden"
                onChange={(e) => void handleFiles(e.target.files)}
            />

            <Dialog
                open={open}
                title={`Amazon CSV インポート — プレビュー (${rows.length} 件)`}
                maxWidth="xl"
                className="max-h-[85vh] flex flex-col"
                onClose={() => setOpen(false)}
            >
                <DialogBody className="overflow-auto flex-1 !py-0 !px-0">
                    <table className="w-full text-xs">
                        <thead className="bg-gray-50 dark:bg-gray-700 sticky top-0">
                            <tr>
                                <th className={th}>CSV タイトル</th>
                                <th className={th}>著者</th>
                                <th className={th}>シリーズ</th>
                                <th className={th}>巻</th>
                                <th className={th}>出版社</th>
                                <th className={th}>対応書籍</th>
                            </tr>
                        </thead>
                        <tbody>
                            {rows.map((r, i) => (
                                <tr
                                    key={i}
                                    className="border-t border-gray-100 dark:border-gray-700"
                                >
                                    <td className={td} title={r.csv_title}>
                                        <span className="line-clamp-2">{r.csv_title}</span>
                                    </td>
                                    <td className={td}>{r.authors.join(', ')}</td>
                                    <td className={td}>{r.series_id}</td>
                                    <td className={td}>{r.volume ?? '—'}</td>
                                    <td className={td}>{r.publisher}</td>
                                    <td className={td}>
                                        <select
                                            value={overrides[i] ?? r.matched_book ?? ''}
                                            onChange={(e) =>
                                                setOverrides((prev) => ({
                                                    ...prev,
                                                    [i]: e.target.value,
                                                }))
                                            }
                                            className="w-full text-xs border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-1 py-0.5"
                                        >
                                            <option value="">（スキップ）</option>
                                            {books.map((b) => (
                                                <option key={b.name} value={b.name}>
                                                    {b.name}
                                                </option>
                                            ))}
                                        </select>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </DialogBody>

                {error && (
                    <p className="px-4 py-2 text-xs text-red-600 dark:text-red-400">{error}</p>
                )}

                <DialogFooter>
                    <DialogCancelButton onClick={() => setOpen(false)} disabled={saving} />
                    <DialogPrimaryButton onClick={() => void handleApply()} disabled={saving}>
                        {saving ? '保存中...' : '保存'}
                    </DialogPrimaryButton>
                </DialogFooter>
            </Dialog>

            <ToastContainer toasts={toasts} onDismiss={dismissToast} />
        </>
    );
}

const th = 'px-3 py-2 text-left font-medium text-gray-700 dark:text-gray-300';
const td = 'px-3 py-2 text-gray-800 dark:text-gray-200 align-top';
