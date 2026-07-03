/**
 * novel 書籍メタ手動編集モーダル（4.3）。
 * BookCard の「編集」ボタンから開く。
 */
import { useEffect, useState } from 'react';

import { patchNovelBookMeta } from '@/features/novel_db/api';
import { buildNovelMetaPatch } from '@/features/novel_db/bookMetaPatch';
import type { BookSummary } from '@/features/novel_db/types';
import {
    Dialog,
    DialogBody,
    DialogCancelButton,
    DialogFooter,
    DialogPrimaryButton,
} from '@/components/ui/dialog';

interface Props {
    book: BookSummary | null;
    onClose: () => void;
    onSaved: () => void;
}

export default function BookMetaEditModal({ book, onClose, onSaved }: Props) {
    const [authors, setAuthors] = useState('');
    const [seriesId, setSeriesId] = useState('');
    const [volume, setVolume] = useState('');
    const [publisher, setPublisher] = useState('');
    const [asin, setAsin] = useState('');
    const [isbn, setIsbn] = useState('');
    const [isbnTouched, setIsbnTouched] = useState(false);
    const [releaseDate, setReleaseDate] = useState('');
    const [releaseDateTouched, setReleaseDateTouched] = useState(false);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (!book) return;
        setAuthors(book.authors.join(', '));
        setSeriesId(book.series_id ?? '');
        setVolume(book.volume != null ? String(book.volume) : '');
        setPublisher(book.publisher ?? '');
        setAsin(book.asin ?? '');
        // BookSummary は isbn/release_date を持たないため、未編集時は PATCH payload から
        // 除外する（バックエンドは空文字を「既存値のクリア」として扱うため、空文字で
        // 送ると既存の ISBN・発売日が意図せず消える）。
        setIsbn('');
        setIsbnTouched(false);
        setReleaseDate('');
        setReleaseDateTouched(false);
        setError(null);
    }, [book]);

    const handleSave = async () => {
        setSaving(true);
        setError(null);
        try {
            const volNum = volume.trim() ? parseInt(volume.trim(), 10) : null;
            await patchNovelBookMeta(
                `${book!.name}.pdf`,
                buildNovelMetaPatch({
                    authors,
                    seriesId,
                    volNum,
                    publisher,
                    asin,
                    isbn,
                    isbnTouched,
                    releaseDate,
                    releaseDateTouched,
                }),
            );
            onSaved();
            onClose();
        } catch {
            setError('保存に失敗しました。');
        } finally {
            setSaving(false);
        }
    };

    return (
        <Dialog open={Boolean(book)} title={book?.name ?? ''} maxWidth="md" onClose={onClose}>
            <DialogBody>
                <div className="space-y-3">
                    <Field label="著者（カンマ区切り）" htmlFor="book-meta-authors">
                        <input
                            id="book-meta-authors"
                            type="text"
                            value={authors}
                            onChange={(e) => setAuthors(e.target.value)}
                            className={inputClass}
                            placeholder="石田 リンネ, 起家 一子"
                        />
                    </Field>
                    <Field label="シリーズ名" htmlFor="book-meta-series">
                        <input
                            id="book-meta-series"
                            type="text"
                            value={seriesId}
                            onChange={(e) => setSeriesId(e.target.value)}
                            className={inputClass}
                            placeholder="おこぼれ姫と円卓の騎士"
                        />
                    </Field>
                    <Field label="巻番号" htmlFor="book-meta-volume">
                        <input
                            id="book-meta-volume"
                            type="number"
                            min={1}
                            value={volume}
                            onChange={(e) => setVolume(e.target.value)}
                            className={inputClass}
                            placeholder="1"
                        />
                    </Field>
                    <Field label="出版社・レーベル" htmlFor="book-meta-publisher">
                        <input
                            id="book-meta-publisher"
                            type="text"
                            value={publisher}
                            onChange={(e) => setPublisher(e.target.value)}
                            className={inputClass}
                            placeholder="ビーズログ文庫"
                        />
                    </Field>
                    <Field label="ASIN" htmlFor="book-meta-asin">
                        <input
                            id="book-meta-asin"
                            type="text"
                            value={asin}
                            onChange={(e) => setAsin(e.target.value)}
                            className={inputClass}
                            placeholder="B009IMAVXC"
                        />
                    </Field>
                    <Field label="ISBN" htmlFor="book-meta-isbn">
                        <input
                            id="book-meta-isbn"
                            type="text"
                            value={isbn}
                            onChange={(e) => {
                                setIsbn(e.target.value);
                                setIsbnTouched(true);
                            }}
                            className={inputClass}
                            placeholder="9784047264298"
                        />
                    </Field>
                    <Field label="発売日" htmlFor="book-meta-release-date">
                        <input
                            id="book-meta-release-date"
                            type="date"
                            value={releaseDate}
                            onChange={(e) => {
                                setReleaseDate(e.target.value);
                                setReleaseDateTouched(true);
                            }}
                            className={inputClass}
                        />
                    </Field>
                    {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}
                </div>
            </DialogBody>
            <DialogFooter>
                <DialogCancelButton onClick={onClose} disabled={saving} />
                <DialogPrimaryButton onClick={() => void handleSave()} disabled={saving}>
                    {saving ? '保存中...' : '保存'}
                </DialogPrimaryButton>
            </DialogFooter>
        </Dialog>
    );
}

const inputClass =
    'w-full px-2.5 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-primary-500';

function Field({
    label,
    htmlFor,
    children,
}: {
    label: string;
    htmlFor: string;
    children: React.ReactNode;
}) {
    return (
        <div>
            <label
                htmlFor={htmlFor}
                className="block text-xs text-gray-600 dark:text-gray-400 mb-1"
            >
                {label}
            </label>
            {children}
        </div>
    );
}
