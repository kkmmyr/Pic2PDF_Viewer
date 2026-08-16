import { BookOpen, Check, Circle } from 'lucide-react';

import type { ReadState } from '@/types';

const STATE_STYLE: Record<ReadState, string> = {
    unread: 'bg-sky-100 text-sky-800 dark:bg-sky-900/50 dark:text-sky-200',
    reading: 'bg-accent-100 text-accent-800 dark:bg-accent-900/50 dark:text-accent-200',
    done: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/50 dark:text-emerald-200',
};

const STATE_LABEL: Record<ReadState, string> = {
    unread: '未読',
    reading: '読書中',
    done: '読了',
};

function StateIcon({ state }: { state: ReadState }) {
    if (state === 'reading') return <BookOpen aria-hidden="true" className="h-3.5 w-3.5" />;
    if (state === 'done') return <Check aria-hidden="true" className="h-3.5 w-3.5" />;
    return <Circle aria-hidden="true" className="h-3.5 w-3.5" />;
}

export function ReadStatePill({ state }: { state: ReadState }) {
    return (
        <span
            className={`inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs font-semibold ${STATE_STYLE[state]}`}
        >
            <StateIcon state={state} />
            {STATE_LABEL[state]}
        </span>
    );
}
