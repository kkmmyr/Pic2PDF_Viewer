import { API_CONFIG } from '@/config/api';

export type ImageZoom = 'fit' | 'double';

type Props = {
    bookName: string;
    pageNo: number;
    imageUrl: string;
    zoom: ImageZoom;
    onZoomChange: (zoom: ImageZoom) => void;
};

export function OCRQaImageViewer({ bookName, pageNo, imageUrl, zoom, onZoomChange }: Props) {
    return (
        <div className="min-w-0">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <h3 className="font-semibold">原画像 — 画面 {pageNo}</h3>
                <div
                    role="group"
                    aria-label="原画像の表示倍率"
                    className="flex rounded-lg border border-gray-300 p-0.5 dark:border-gray-600"
                >
                    {(
                        [
                            ['fit', '画面幅'],
                            ['double', '2倍'],
                        ] as const
                    ).map(([value, label]) => (
                        <button
                            key={value}
                            type="button"
                            aria-pressed={zoom === value}
                            onClick={() => onZoomChange(value)}
                            className={`rounded-md px-2.5 py-1 text-xs font-medium ${
                                zoom === value
                                    ? 'bg-primary-600 text-white'
                                    : 'text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800'
                            }`}
                        >
                            {label}
                        </button>
                    ))}
                </div>
            </div>
            <div
                key={pageNo}
                role="region"
                // Scroll regions need focus so arrow keys work without a pointer.
                // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex
                tabIndex={0}
                aria-label="拡大した原画像。上下方向はホイール、トラックパッド、矢印キーで移動できます"
                className="h-[calc(100dvh-8rem)] min-h-[640px] max-h-[1200px] overflow-x-hidden overflow-y-auto rounded-lg bg-gray-100 p-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-500 dark:bg-gray-950"
            >
                <img
                    src={`${API_CONFIG.BASE_URL}${imageUrl}`}
                    alt={`${bookName} 画面 ${pageNo}`}
                    className="h-auto w-full object-contain"
                />
            </div>
        </div>
    );
}
