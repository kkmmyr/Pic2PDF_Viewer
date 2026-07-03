import type { ReactNode } from 'react';

interface ErrorFallbackCardProps {
    message: string;
    action: ReactNode;
}

export function ErrorFallbackCard({ message, action }: ErrorFallbackCardProps) {
    return (
        <div className="flex justify-center items-center min-h-[60vh] p-5">
            <div className="p-10 border-2 border-red-500 rounded-xl max-w-lg w-full text-center bg-white dark:bg-gray-900 shadow-md">
                <span className="text-5xl block mb-3">⚠️</span>
                <h2 className="text-red-600 text-2xl font-bold mb-3">エラーが発生しました</h2>
                <p className="text-gray-500 dark:text-gray-400 mb-6 break-words">{message}</p>
                {action}
            </div>
        </div>
    );
}
