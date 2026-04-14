import { useEffect, useRef, useState } from 'react';
import { FileText } from 'lucide-react';
import { buildStaticUrl } from '../../config/api';

interface LazyThumbnailProps {
    src: string | null;
    alt: string;
    className?: string;
}

/**
 * Intersection Observer を使ったサムネイル遅延読み込みコンポーネント。
 * 画面内に入った時点で初めて img の src をセットする。
 */
export function LazyThumbnail({ src, alt, className = '' }: LazyThumbnailProps) {
    const ref = useRef<HTMLDivElement>(null);
    const [isVisible, setIsVisible] = useState(false);
    const [hasError, setHasError] = useState(false);

    useEffect(() => {
        const el = ref.current;
        if (!el) return;

        const observer = new IntersectionObserver(
            ([entry]) => {
                if (entry.isIntersecting) {
                    setIsVisible(true);
                    observer.disconnect();
                }
            },
            { rootMargin: '200px' } // 200px 手前からプリロード開始
        );
        observer.observe(el);
        return () => observer.disconnect();
    }, []);

    return (
        <div ref={ref} className={`w-full h-full flex items-center justify-center bg-gray-100 dark:bg-gray-700 ${className}`}>
            {isVisible && src && !hasError ? (
                <img
                    src={buildStaticUrl(src)}
                    alt={alt}
                    className="w-full h-full object-cover"
                    onError={() => setHasError(true)}
                />
            ) : (
                <div className="w-full h-full flex items-center justify-center bg-gray-100 dark:bg-gray-700">
                    <FileText className="w-12 h-12 text-gray-300 dark:text-gray-600" />
                </div>
            )}
        </div>
    );
}
