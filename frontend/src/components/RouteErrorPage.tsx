import { useRouteError, isRouteErrorResponse, Link } from 'react-router-dom';
import { ErrorFallbackCard } from '@/components/ui/ErrorFallbackCard';

export default function RouteErrorPage() {
    const error = useRouteError();
    const message = isRouteErrorResponse(error)
        ? `${error.status} ${error.statusText}`
        : error instanceof Error
          ? error.message
          : '不明なエラーが発生しました。';

    return (
        <ErrorFallbackCard
            message={message}
            action={
                <Link
                    to="/"
                    className="inline-block bg-red-500 text-white px-7 py-2.5 rounded-lg text-base hover:bg-red-600 transition-colors"
                >
                    トップへ戻る
                </Link>
            }
        />
    );
}
