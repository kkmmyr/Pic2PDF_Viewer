import { Suspense } from 'react';
import { Outlet, useSearchParams } from 'react-router-dom';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { GlobalNavigation } from '@/components/GlobalNavigation';
import { Toaster } from 'sonner';

export default function Layout() {
    const [searchParams] = useSearchParams();
    const isReaderMode = searchParams.has('file');

    return (
        <div className="min-h-screen bg-gray-50 dark:bg-gray-950 flex flex-col font-sans text-gray-900 dark:text-gray-100">
            {!isReaderMode && <GlobalNavigation />}
            <main className="flex-1 w-full mx-auto">
                <ErrorBoundary>
                    <Suspense fallback={null}>
                        <Outlet />
                    </Suspense>
                </ErrorBoundary>
            </main>
            <Toaster position="bottom-right" richColors />
        </div>
    );
}
