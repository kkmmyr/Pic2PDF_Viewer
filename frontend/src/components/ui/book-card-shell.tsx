import type { ReactNode } from 'react';

type BookCardTone = 'default' | 'selected' | 'group';

interface BookCardShellProps {
    cover: ReactNode;
    title: string;
    displayTitle?: string;
    tone?: BookCardTone;
    authors?: ReactNode;
    meta?: ReactNode;
    summary?: ReactNode;
    footer?: ReactNode;
}

const TONE_CLASS: Record<BookCardTone, string> = {
    default: 'border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-800',
    selected: 'border-amber-400 bg-amber-50 dark:bg-amber-900/20',
    group: 'border-accent-300 bg-white dark:border-accent-700 dark:bg-gray-800',
};

export function BookCardShell({
    cover,
    title,
    displayTitle = title,
    tone = 'default',
    authors,
    meta,
    summary,
    footer,
}: BookCardShellProps) {
    return (
        <article
            className={`relative flex h-full flex-col overflow-hidden rounded-lg border-2 shadow-md transition-shadow hover:shadow-lg ${TONE_CLASS[tone]}`}
        >
            {cover}
            <div className="flex flex-1 flex-col gap-1.5 p-2.5">
                <h3
                    className={`line-clamp-2 text-sm font-semibold leading-snug ${tone === 'group' ? 'text-accent-700 dark:text-accent-300' : 'text-gray-900 dark:text-gray-100'}`}
                    title={displayTitle}
                >
                    {displayTitle}
                </h3>
                {authors}
                {meta}
                {summary}
                {footer && (
                    <div className="mt-auto flex min-h-11 items-center border-t border-gray-200 pt-1 dark:border-gray-700">
                        {footer}
                    </div>
                )}
            </div>
        </article>
    );
}
