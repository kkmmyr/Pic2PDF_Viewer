import { ArrowLeft, Home, User, Library, ChevronRight } from 'lucide-react';
import type { LibrarySource } from '../../types';
import { SourceSelector } from './SourceSelector';

export interface LibraryBreadcrumb {
    kind: 'home' | 'author' | 'series';
    label: string;
    onClick?: () => void;
}

interface LibraryNavBarProps {
    currentPath: string;
    currentSource: LibrarySource;
    breadcrumbs: LibraryBreadcrumb[];
    onUpClick: () => void;
    onSourceChange: (source: LibrarySource) => void;
}

export function LibraryNavBar({ currentPath, currentSource, breadcrumbs, onUpClick, onSourceChange }: LibraryNavBarProps) {
    return (
        <div className="h-12 flex items-center px-4 justify-between gap-4">
            <div className="flex items-center gap-3 flex-1 min-w-0">
                {currentPath && (
                    <button
                        onClick={onUpClick}
                        className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-full shrink-0"
                    >
                        <ArrowLeft className="w-5 h-5 text-gray-700 dark:text-gray-300" />
                    </button>
                )}
                <h1 className="font-semibold truncate text-gray-900 dark:text-gray-100 shrink-0">
                    {currentPath ? currentPath.split('/').pop() : 'Library'}
                </h1>
                {breadcrumbs.length > 0 && (
                    <div className="flex items-center gap-1.5 text-sm text-gray-700 dark:text-gray-300 min-w-0 overflow-hidden">
                        <span className="text-gray-300 dark:text-gray-600 shrink-0">|</span>
                        {breadcrumbs.map((crumb, i) => {
                            const isLast = i === breadcrumbs.length - 1;
                            const Icon = crumb.kind === 'home' ? Home : crumb.kind === 'author' ? User : Library;
                            const labelEl = (
                                <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded ${
                                    isLast
                                        ? 'bg-purple-100 dark:bg-purple-900/40 text-purple-700 dark:text-purple-300 font-medium'
                                        : crumb.onClick
                                            ? 'hover:bg-gray-200 dark:hover:bg-gray-800 cursor-pointer'
                                            : ''
                                }`}>
                                    <Icon className="w-3.5 h-3.5" />
                                    <span className="truncate max-w-[180px]">{crumb.label}</span>
                                </span>
                            );
                            return (
                                <span key={`${crumb.kind}-${i}`} className="inline-flex items-center gap-1 shrink-0">
                                    {i > 0 && <ChevronRight className="w-3.5 h-3.5 text-gray-400 dark:text-gray-500 shrink-0" />}
                                    {crumb.onClick && !isLast
                                        ? <button onClick={crumb.onClick}>{labelEl}</button>
                                        : labelEl}
                                </span>
                            );
                        })}
                    </div>
                )}
            </div>
            <SourceSelector currentSource={currentSource} onSourceChange={onSourceChange} />
        </div>
    );
}
