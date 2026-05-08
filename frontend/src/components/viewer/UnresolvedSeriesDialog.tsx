import { useEffect, useState } from 'react';
import { Dialog, DialogBody, DialogFooter, DialogCancelButton } from '../ui/Dialog';
import {
    useUnresolvedSeriesCandidates,
    type UnresolvedSeriesCandidate,
    type UnresolvedReason,
} from '../../hooks/useUnresolvedSeriesCandidates';
import type { LibrarySource } from '../../types';
import { API_ENDPOINTS } from '../../config/api';
import apiClient from '../../config/api_client';

interface UnresolvedSeriesDialogProps {
    open: boolean;
    source: LibrarySource;
    onClose: () => void;
    /** シリーズ化が完了したときに親 meta を再取得するためのコールバック */
    onComplete: () => void;
}

const REASON_LABEL: Record<UnresolvedReason, string> = {
    short_prefix: 'プレフィックスが短い',
    volume_parse_failed: '巻数解析失敗',
};

const REASON_BADGE_CLS: Record<UnresolvedReason, string> = {
    short_prefix: 'bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300',
    volume_parse_failed: 'bg-rose-100 dark:bg-rose-900/40 text-rose-700 dark:text-rose-300',
};

/**
 * シリーズ自動判定で漏れた候補ペアをレビューしてシリーズ化するダイアログ（A-6）。
 *
 * 各候補の共通プレフィックスを編集可能なタイトル入力にプレ充填し、
 * 「シリーズ化」ボタンで `POST /api/series/assign` を直接呼ぶ。
 * 完了後は候補リストを再取得し、親に `onComplete` で meta refresh を促す。
 */
export function UnresolvedSeriesDialog({
    open,
    source,
    onClose,
    onComplete,
}: UnresolvedSeriesDialogProps) {
    const { candidates, loading, error, refresh, reset } = useUnresolvedSeriesCandidates(source);

    useEffect(() => {
        if (open) {
            refresh();
        } else {
            reset();
        }
    }, [open, refresh, reset]);

    return (
        <Dialog
            open={open}
            title="未分類シリーズ候補をレビュー"
            subtitle="自動判定で漏れた候補。タイトルを確認してシリーズ化できる"
            onClose={onClose}
            maxWidth="lg"
        >
            <DialogBody>
                {loading && (
                    <p className="text-sm text-gray-500 dark:text-gray-400">読み込み中...</p>
                )}
                {error && <p className="text-sm text-rose-500 dark:text-rose-400">{error}</p>}
                {!loading && !error && candidates && candidates.length === 0 && (
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                        未分類の候補はありません。
                    </p>
                )}
                {!loading && candidates && candidates.length > 0 && (
                    <ul className="space-y-3">
                        {candidates.map((c, i) => (
                            <CandidateRow
                                key={`${c.common_prefix}-${i}`}
                                candidate={c}
                                source={source}
                                onAssigned={() => {
                                    refresh();
                                    onComplete();
                                }}
                            />
                        ))}
                    </ul>
                )}
            </DialogBody>
            <DialogFooter>
                <DialogCancelButton onClick={onClose}>閉じる</DialogCancelButton>
            </DialogFooter>
        </Dialog>
    );
}

interface CandidateRowProps {
    candidate: UnresolvedSeriesCandidate;
    source: LibrarySource;
    onAssigned: () => void;
}

function CandidateRow({ candidate, source, onAssigned }: CandidateRowProps) {
    const [title, setTitle] = useState(candidate.common_prefix);
    const [submitting, setSubmitting] = useState(false);
    const [rowError, setRowError] = useState<string | null>(null);

    const handleAssign = async () => {
        const trimmed = title.trim();
        if (!trimmed) {
            setRowError('シリーズタイトルを入力してください。');
            return;
        }
        setSubmitting(true);
        setRowError(null);
        try {
            const indexes = candidate.books.map((_, i) => i + 1);
            await apiClient.post(API_ENDPOINTS.SERIES_ASSIGN, {
                path: candidate.books[0].path,
                names: candidate.books.map((b) => b.name),
                title: trimmed,
                index: indexes,
                source,
            });
            onAssigned();
        } catch (e) {
            setRowError(e instanceof Error ? e.message : 'シリーズ化に失敗しました。');
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <li className="border border-gray-200 dark:border-gray-700 rounded-md p-3 bg-gray-50 dark:bg-gray-900">
            <div className="flex items-center gap-2 mb-2">
                <span
                    className={`text-xs px-2 py-0.5 rounded-full font-medium ${REASON_BADGE_CLS[candidate.reason]}`}
                >
                    {REASON_LABEL[candidate.reason]}
                </span>
                <span className="text-xs text-gray-500 dark:text-gray-400 tabular-nums">
                    類似度 {(candidate.score * 100).toFixed(0)}%
                </span>
            </div>
            <ul className="text-sm text-gray-700 dark:text-gray-300 space-y-1 mb-2">
                {candidate.books.map((b, i) => (
                    <li key={b.name} className="flex items-center gap-2 truncate">
                        <span className="text-accent-600 dark:text-accent-400 tabular-nums shrink-0 font-medium">
                            #{i + 1}
                        </span>
                        <span className="truncate">{b.title}</span>
                    </li>
                ))}
            </ul>
            <div className="flex items-center gap-2">
                <input
                    type="text"
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    placeholder="シリーズタイトル"
                    className="flex-1 px-2 py-1 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-sm text-gray-800 dark:text-gray-200"
                    disabled={submitting}
                />
                <button
                    onClick={handleAssign}
                    disabled={submitting}
                    className="px-3 py-1 text-sm bg-accent-600 hover:bg-accent-700 disabled:opacity-60 text-white rounded shrink-0"
                >
                    {submitting ? '登録中...' : 'シリーズ化'}
                </button>
            </div>
            {rowError && (
                <p className="mt-1.5 text-xs text-rose-500 dark:text-rose-400">{rowError}</p>
            )}
        </li>
    );
}
