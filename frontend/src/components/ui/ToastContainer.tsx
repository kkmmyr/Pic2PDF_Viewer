import { X } from 'lucide-react';
import type { Toast } from '../../hooks/useToast';

interface ToastContainerProps {
    toasts: Toast[];
    onDismiss: (id: number) => void;
}

const TYPE_STYLES = {
    success: 'bg-green-600 text-white',
    error: 'bg-red-600 text-white',
    info: 'bg-gray-800 text-white',
} as const;

export function ToastContainer({ toasts, onDismiss }: ToastContainerProps) {
    if (toasts.length === 0) return null;

    return (
        <div className="fixed bottom-4 right-4 z-toast flex flex-col gap-2">
            {toasts.map((toast) => (
                <div
                    key={toast.id}
                    className={`flex items-center gap-3 px-4 py-3 rounded-lg shadow-lg text-sm max-w-sm animate-in slide-in-from-right-4 duration-200 ${TYPE_STYLES[toast.type]}`}
                >
                    <span className="flex-1">{toast.message}</span>
                    <button
                        onClick={() => onDismiss(toast.id)}
                        className="shrink-0 opacity-70 hover:opacity-100"
                    >
                        <X className="w-4 h-4" />
                    </button>
                </div>
            ))}
        </div>
    );
}
