import type { ReactNode } from 'react';
import { BookOpen, Download, Link2, ScanLine } from 'lucide-react';
import { NavLink } from 'react-router-dom';

import { cn } from '@/lib/utils';

const TABS = [
    { to: '/kindle/catalog', label: '購入書籍', icon: BookOpen },
    { to: '/kindle/links', label: '画像紐付け', icon: Link2 },
    { to: '/kindle/capture', label: 'キャプチャ', icon: ScanLine },
    { to: '/kindle/imports', label: '取込・管理', icon: Download },
] as const;

interface KindlePageShellProps {
    title: string;
    description: string;
    actions?: ReactNode;
    children: ReactNode;
}

export function KindlePageShell({ title, description, actions, children }: KindlePageShellProps) {
    return (
        <div className="mx-auto w-full max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
            <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">{title}</h1>
                    <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{description}</p>
                </div>
                {actions}
            </div>

            <nav
                aria-label="Kindle カタログ"
                className="mt-5 grid grid-cols-2 gap-2 rounded-xl border border-gray-200 bg-white p-2 dark:border-gray-700 dark:bg-gray-900 sm:flex"
            >
                {TABS.map((tab) => (
                    <NavLink
                        key={tab.to}
                        to={tab.to}
                        end
                        className={({ isActive }) =>
                            cn(
                                'inline-flex min-h-10 items-center justify-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                                isActive
                                    ? 'bg-primary-50 text-primary-700 dark:bg-primary-900/30 dark:text-primary-300'
                                    : 'text-gray-600 hover:bg-gray-50 dark:text-gray-400 dark:hover:bg-gray-800',
                            )
                        }
                    >
                        <tab.icon className="h-4 w-4" />
                        {tab.label}
                    </NavLink>
                ))}
            </nav>

            <div className="mt-5">{children}</div>
        </div>
    );
}
