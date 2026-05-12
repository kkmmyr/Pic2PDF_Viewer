/**
 * novel 書籍メタ手動編集モーダル（4.3）。
 * BookCard の「編集」ボタンから開く。
 */
import { useEffect, useState } from 'react';
import { X } from 'lucide-react';

import { patchNovelBookMeta } from '../../features/novel_db/api';
import type { BookSummary } from '../../features/novel_db/types';

interface Props {
    book: BookSummary | null;
    onClose: () => void;
    onSaved: () => void;
}

function splitAuthors(raw: string): string[] {
    return raw
        .split(/[,、]/)
        .map((s) => s.trim())
        .filter(Boolean);
}

export default function BookMetaEditModal({ book, onClose, onSaved }: Props) {
    const [authors, setAuthors] = useState('');
    const [seriesId, setSeriesId] = useState('');
    const [volume, setVolume] = useState('');
    const [publisher, setPublisher] = useState('');
    const [asin, setAsin] = useState('');
    const [isbn, setIsbn] = useState('');
    const [releaseDate, setReleaseDate] = useState('');
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (!book) return;
        setAuthors(book.authors.join(', '));
        setSeriesId(book.series_id ?? '');
        setVolume(book.volume != null ? String(book.volume) : '');
        setPublisher(book.publisher ?? '');
        setAsin(book.asin ?? '');
        setIsbn('');
        setReleaseDate('');
        setError(null);
    }, [book]);

    if (!book) return null;

    const handleSave = async () => {
        setSaving(true);
        setError(null);
        try {
            const volNum = volume.trim() ? parseInt(volume.trim(), 10) : null;
            await patchNovelBookMeta(`${book.name}.pdf`, {
                authors: splitAuthors(authors),
                series_id: seriesId.trim(),
                ...(volNum != null ? { volume: volNum } : { volume_clear: true }),
                publisher: publisher.trim(),
                asin: asin.trim(),
                isbn: isbn.trim(),
                release_date: releaseDate.trim(),
            });
            onSaved();
            onClose();
        } catch {
            setError('保存に失敗しました。');
        } finally {
            setSaving(false);
        }
    };

    return (
        <div
            className="fixed inset-0 z-modal bg-black/50 flex items-center justify-center p-4"
            onClick={onClose}
        >
            <div
                className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-md"
                onClick={(e) => e.stopPropagation()}
            >
                <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700">
                    <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">
                        {book.name}
                    </h2>
                    <button onClick={onClose} aria-label="閉じる">
                        <X className="w-4 h-4 text-gray-500" />
                    </button>
                </div>
                <div className="px-4 py-4 space-y-3">
                    <Field label="著者（カンマ区切り）">
                        <input
                            type="text"
                            value={authors}
                            onChange={(e) => setAuthors(e.target.value)}
                            className={inputClass}
                            placeholder="石田 リンネ, 起家 一子"
                        />
                    </Field>
                    <Field label="シリーズ名">
                        <input
                            type="text"
                            value={seriesId}
                            onChange={(e) => setSeriesId(e.target.value)}
                            className={inputClass}
                            placeholder="おこぼれ姫と円卓の騎士"
                        />
                    </Field>
                    <Field label="巻番号">
                        <input
                            type="number"
                            min={1}
                            value={volume}
                            onChange={(e) => setVolume(e.target.value)}
                            className={inputClass}
                            placeholder="1"
                        />
                    </Field>
                    <Field label="出版社・レーベル">
                        <input
                            type="text"
                            value={publisher}
                            onChange={(e) => setPublisher(e.target.value)}
                            className={inputClass}
                            placeholder="ビーズログ文庫"
                        />
                    </Field>
                    <Field label="ASIN">
                        <input
                            type="text"
                            value={asin}
                            onChange={(e) => setAsin(e.target.value)}
                            className={inputClass}
                            placeholder="B009IMAVXC"
                        />
                    </Field>
                    <Field label="ISBN">
                        <input
                            type="text"
                            value={isbn}
                            onChange={(e) => setIsbn(e.target.value)}
                            className={inputClass}
                            placeholder="9784047264298"
                        />
                    </Field>
                    <Field label="発売日">
                        <input
                            type="date"
                            value={releaseDate}
                            onChange={(e) => setReleaseDate(e.target.value)}
                            className={inputClass}
                        />
                    </Field>
                    {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}
                </div>
                <div className="flex justify-end gap-2 px-4 py-3 border-t border-gray-200 dark:border-gray-700">
                    <button
                        onClick={onClose}
                        className="px-3 py-1.5 text-xs rounded border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700"
                    >
                        キャンセル
                    </button>
                    <button
                        onClick={() => void handleSave()}
                        disabled={saving}
                        className="px-3 py-1.5 text-xs rounded bg-primary-600 hover:bg-primary-700 text-white disabled:opacity-50"
                    >
                        {saving ? '保存中...' : '保存'}
                    </button>
                </div>
            </div>
        </div>
    );
}

const inputClass =
    'w-full px-2.5 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-primary-500';

function Field({ label, children }: { label: string; children: React.ReactNode }) {
    return (
        <div>
            <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1">{label}</label>
            {children}
        </div>
    );
}
