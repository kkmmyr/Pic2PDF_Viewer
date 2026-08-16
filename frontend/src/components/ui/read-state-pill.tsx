import { BookOpen, Check, Circle } from 'lucide-react';

import type { ReadState } from '@/types';

const STATE_LABEL: Record<ReadState, string> = {
    unread: '未読',
    reading: '読書中',
    done: '読了',
};

const STATE_STYLE: Record<ReadState, string> = {
    unread: 'bg-sky-100 text-sky-600 dark:bg-sky-900/40 dark:text-sky-300',
    reading: 'bg-accent-100 text-accent-700 dark:bg-accent-900/40 dark:text-accent-300',
    done: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300',
};

const STATE_ICON = {
    unread: Circle,
    reading: BookOpen,
    done: Check,
} satisfies Record<ReadState, typeof Circle>;

export function ReadStatePill({ state }: { state: ReadState }) {
    const Icon = STATE_ICON[state];

    return (
        <span
            role="img"
            aria-label={STATE_LABEL[state]}
            title={STATE_LABEL[state]}
            className={`inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full ${STATE_STYLE[state]}`}
        >
            <Icon aria-hidden="true" className="h-3 w-3" />
        </span>
    );
}
