import { Alert } from '@/components/ui/alert';

type Props = { isError: boolean; isLoading: boolean; awaitingCount: number };

export function OCRQaRunState({ isError, isLoading, awaitingCount }: Props) {
    if (isError) {
        return (
            <Alert variant="error" className="m-4">
                QA対象の取得に失敗しました。
            </Alert>
        );
    }
    if (!isLoading && awaitingCount === 0) {
        return (
            <div className="px-5 py-8 text-center text-sm text-gray-500">
                品質確認待ちのOCR結果はありません。
            </div>
        );
    }
    return null;
}
