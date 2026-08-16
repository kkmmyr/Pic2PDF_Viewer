import { useState } from 'react';
import { Check, Link2, Loader2 } from 'lucide-react';
import { toast } from 'sonner';

import { KindlePageShell } from '@/components/kindle/KindlePageShell';
import { bookTypeLabel } from '@/components/kindle/kindle-labels';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { useKindleLinkCandidates, useKindleLinking } from '@/features/kindle/queries';
import type { KindleLinkCandidate } from '@/features/kindle/types';
import { errorMessage } from '@/utils/error';

export function KindleLinksScreen() {
    const linking = useKindleLinking();
    const [selectedKey, setSelectedKey] = useState('');
    const [candidateToConfirm, setCandidateToConfirm] = useState<KindleLinkCandidate | null>(null);
    const selectedBook =
        linking.unlinked.find((book) => `${book.source}:${book.book_id}` === selectedKey) ?? null;
    const candidates = useKindleLinkCandidates(
        selectedBook?.source ?? null,
        selectedBook?.book_id ?? null,
    );
    const selectedIndex = selectedBook
        ? linking.unlinked.findIndex(
              (book) =>
                  book.source === selectedBook.source && book.book_id === selectedBook.book_id,
          )
        : -1;

    const confirmLink = async () => {
        if (!selectedBook || !candidateToConfirm) return;
        try {
            await linking.link({
                source: selectedBook.source,
                bookId: selectedBook.book_id,
                asin: candidateToConfirm.asin,
            });
            toast.success('既存画像へ ASIN を紐付けました');
            setCandidateToConfirm(null);
            setSelectedKey('');
        } catch (error) {
            toast.error(errorMessage(error, 'ASIN の紐付けに失敗しました'));
        }
    };

    return (
        <KindlePageShell
            title="既存画像の紐付け"
            description="Pic2PDFViewerの既存画像とKindle購入カタログを比較してASINを設定します"
        >
            <Alert variant="info" className="mb-4">
                候補スコアは判断材料です。候補を表示・選択しただけでは更新されず、最終確認後だけASINを設定します。
            </Alert>

            {linking.error && (
                <Alert variant="error" className="mb-4">
                    {errorMessage(linking.error, '未紐付け画像を取得できませんでした')}
                </Alert>
            )}

            <div className="grid gap-4 lg:grid-cols-[minmax(280px,0.85fr)_minmax(0,1.65fr)]">
                <section className="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-900">
                    <div className="flex items-center justify-between gap-3">
                        <div>
                            <h2 className="font-semibold">紐付け対象</h2>
                            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                                未紐付け {linking.unlinked.length} 件
                            </p>
                        </div>
                        {selectedIndex >= 0 && (
                            <span className="text-xs text-gray-500">
                                {selectedIndex + 1} / {linking.unlinked.length}
                            </span>
                        )}
                    </div>

                    {linking.isLoading ? (
                        <div className="flex items-center gap-2 py-10 text-sm text-gray-500">
                            <Loader2 className="h-4 w-4 animate-spin" />
                            対象を読み込み中
                        </div>
                    ) : linking.unlinked.length === 0 ? (
                        <div className="py-10 text-center text-sm text-gray-500">
                            未紐付け画像はありません。
                        </div>
                    ) : (
                        <div className="mt-4 max-h-[34rem] space-y-2 overflow-y-auto pr-1">
                            {linking.unlinked.map((book) => {
                                const key = `${book.source}:${book.book_id}`;
                                const selected = key === selectedKey;
                                return (
                                    <button
                                        key={key}
                                        type="button"
                                        aria-pressed={selected}
                                        onClick={() => {
                                            setSelectedKey(key);
                                            setCandidateToConfirm(null);
                                        }}
                                        className={`w-full rounded-lg border p-3 text-left transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 ${
                                            selected
                                                ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20'
                                                : 'border-gray-200 hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-800'
                                        }`}
                                    >
                                        <div className="flex items-start justify-between gap-2">
                                            <span className="text-sm font-medium">
                                                {book.title}
                                            </span>
                                            <span className="shrink-0 rounded-full bg-gray-100 px-2 py-0.5 text-xs dark:bg-gray-800">
                                                {book.source}
                                            </span>
                                        </div>
                                        <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                                            {book.authors.join(' / ') || '著者不明'}
                                        </div>
                                        {book.series_title && (
                                            <div className="mt-1 text-xs text-gray-400">
                                                {book.series_title}
                                            </div>
                                        )}
                                    </button>
                                );
                            })}
                        </div>
                    )}
                </section>

                <section className="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-900">
                    <div className="flex items-center gap-2">
                        <Link2 className="h-5 w-5" />
                        <h2 className="font-semibold">Kindleカタログ候補</h2>
                    </div>

                    {!selectedBook ? (
                        <div className="flex min-h-64 items-center justify-center text-sm text-gray-500">
                            左の一覧から紐付け対象を選択してください。
                        </div>
                    ) : (
                        <>
                            <div className="mt-4 rounded-lg border border-gray-200 bg-gray-50 p-3 text-sm dark:border-gray-700 dark:bg-gray-800/50">
                                <div className="text-xs font-medium text-gray-500 dark:text-gray-400">
                                    比較中の既存画像
                                </div>
                                <div className="mt-1 font-medium">{selectedBook.title}</div>
                                <div className="mt-1 text-xs text-gray-500">
                                    {selectedBook.source} /{' '}
                                    {selectedBook.authors.join(' / ') || '著者不明'}
                                </div>
                            </div>

                            {candidates.isLoading && (
                                <div className="flex items-center gap-2 py-10 text-sm text-gray-500">
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                    候補を検索中
                                </div>
                            )}
                            {candidates.error && (
                                <Alert variant="error" className="mt-4">
                                    {errorMessage(candidates.error, '候補を取得できませんでした')}
                                </Alert>
                            )}
                            <div className="mt-4 space-y-3">
                                {candidates.data?.items.map((candidate) => (
                                    <article
                                        key={candidate.asin}
                                        className="rounded-lg border border-gray-200 p-4 dark:border-gray-700"
                                    >
                                        <div className="flex flex-wrap items-start justify-between gap-3">
                                            <div className="min-w-0 flex-1">
                                                <div className="font-medium">{candidate.title}</div>
                                                <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                                                    {candidate.asin} /{' '}
                                                    {candidate.authors.join(' / ') || '著者不明'}
                                                </div>
                                                <div className="mt-2 flex flex-wrap gap-2 text-xs">
                                                    <span className="rounded-full bg-primary-50 px-2 py-1 text-primary-700 dark:bg-primary-900/30 dark:text-primary-300">
                                                        {bookTypeLabel(candidate.book_type)}
                                                    </span>
                                                    <span className="rounded-full bg-gray-100 px-2 py-1 dark:bg-gray-800">
                                                        スコア {candidate.score}
                                                    </span>
                                                </div>
                                                <div className="mt-2 text-xs text-gray-500">
                                                    {candidate.reasons.join('・') ||
                                                        '候補理由はありません'}
                                                </div>
                                            </div>
                                            <Button
                                                variant="secondary"
                                                disabled={linking.linking}
                                                onClick={() => setCandidateToConfirm(candidate)}
                                            >
                                                <Check className="h-4 w-4" />
                                                この候補を選択
                                            </Button>
                                        </div>
                                    </article>
                                ))}
                            </div>
                            {!candidates.isLoading &&
                                !candidates.error &&
                                (candidates.data?.items.length ?? 0) === 0 && (
                                    <div className="py-10 text-center text-sm text-gray-500">
                                        候補がありません。購入書籍ページでASINを確認してください。
                                    </div>
                                )}
                        </>
                    )}
                </section>
            </div>

            <ConfirmDialog
                open={candidateToConfirm !== null}
                title="このASINを紐付けますか？"
                message={
                    selectedBook && candidateToConfirm
                        ? [
                              `既存画像: ${selectedBook.title}`,
                              `候補書籍: ${candidateToConfirm.title}`,
                              `ASIN: ${candidateToConfirm.asin}`,
                              `著者: ${candidateToConfirm.authors.join(' / ') || '著者不明'}`,
                              `種別: ${bookTypeLabel(candidateToConfirm.book_type)}`,
                              '',
                              '画像の移動や既存メタデータの上書きは行いません。',
                          ].join('\n')
                        : ''
                }
                confirmLabel={linking.linking ? '紐付け中…' : 'ASINを紐付け'}
                confirmDisabled={linking.linking}
                onConfirm={() => void confirmLink()}
                onCancel={() => {
                    if (!linking.linking) setCandidateToConfirm(null);
                }}
            />
        </KindlePageShell>
    );
}
