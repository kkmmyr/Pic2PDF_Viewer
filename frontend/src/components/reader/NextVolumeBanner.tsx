import { ChevronRight } from 'lucide-react';

interface NextVolumeBannerProps {
    title: string;
    onClick: () => void;
}

export function NextVolumeBanner({ title, onClick }: NextVolumeBannerProps) {
    return (
        <button
            onClick={onClick}
            className="fixed bottom-6 left-1/2 -translate-x-1/2 z-floating-action px-4 py-2 rounded-full bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium shadow-lg flex items-center gap-2 transition-colors"
            title={title}
        >
            <span>次の巻へ</span>
            <ChevronRight className="w-4 h-4" />
        </button>
    );
}
