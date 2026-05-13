import { Fragment, type ComponentType } from 'react';
import { Link, Outlet, useLocation, useSearchParams } from 'react-router-dom';
import {
    BookOpen,
    BookText,
    FileText,
    Library,
    MessageSquare,
    Moon,
    Settings,
    Sparkles,
    Sun,
    Wrench,
} from 'lucide-react';
import { useDarkMode } from '../hooks';

interface NavItem {
    to: string;
    label: string;
    icon: ComponentType<{ className?: string }>;
}

interface NavGroup {
    label: string;
    items: NavItem[];
}

const NAV_GROUPS: NavGroup[] = [
    {
        label: '同人誌',
        items: [
            { to: '/doujin', icon: Library, label: 'Library' },
            { to: '/doujin/generator', icon: Settings, label: 'Generator' },
            { to: '/doujin/hitomi', icon: Sparkles, label: '新着' },
        ],
    },
    {
        label: '漫画',
        items: [
            { to: '/comic', icon: Library, label: 'Library' },
        ],
    },
    {
        label: '小説',
        items: [
            { to: '/novel/db', icon: BookOpen, label: 'DB' },
            { to: '/novel/discussion', icon: MessageSquare, label: '読書会' },
            { to: '/novel/manage', icon: Wrench, label: '管理' },
        ],
    },
];

const LINK_CLASS =
    'px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200 flex items-center gap-1.5';
const DIVIDER = <div className="w-px h-5 bg-gray-200 dark:bg-gray-700 mx-1" />;

export default function Layout() {
    const location = useLocation();
    const [searchParams] = useSearchParams();
    const isReaderMode = searchParams.has('file');
    const { isDark, toggle: toggleDark } = useDarkMode();

    const isActive = (path: string) =>
        location.pathname === path
            ? 'text-primary-600 bg-primary-50 dark:text-primary-400 dark:bg-primary-900/30'
            : 'text-gray-600 hover:bg-gray-50 dark:text-gray-400 dark:hover:bg-gray-800';

    return (
        <div className="min-h-screen bg-gray-50 dark:bg-gray-950 flex flex-col font-sans text-gray-900 dark:text-gray-100">
            {!isReaderMode && (
                <header className="bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700 sticky top-0 z-header">
                    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                        <div className="flex justify-between h-16">
                            <div className="flex items-center">
                                <Link to="/" className="flex items-center gap-2">
                                    <div className="bg-primary-600 p-1.5 rounded-lg">
                                        <FileText className="w-6 h-6 text-white" />
                                    </div>
                                    <span className="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-primary-500 to-primary-700">
                                        Pic2PDF Viewer
                                    </span>
                                </Link>
                            </div>

                            <nav className="flex items-center gap-0.5">
                                {NAV_GROUPS.map((group, gi) => (
                                    <Fragment key={group.label}>
                                        {gi > 0 && DIVIDER}
                                        <span className="text-xs text-gray-400 dark:text-gray-500 px-1.5 select-none">
                                            {group.label}
                                        </span>
                                        {group.items.map((item) => (
                                            <Link
                                                key={item.to}
                                                to={item.to}
                                                className={`${LINK_CLASS} ${isActive(item.to)}`}
                                            >
                                                <item.icon className="w-4 h-4" />
                                                {item.label}
                                            </Link>
                                        ))}
                                    </Fragment>
                                ))}

                                {DIVIDER}

                                <a
                                    href="/site/index.html"
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className={`${LINK_CLASS} text-gray-600 hover:bg-gray-50 dark:text-gray-400 dark:hover:bg-gray-800`}
                                    title="設計ドキュメント（別タブで開く）"
                                >
                                    <BookText className="w-4 h-4" />
                                    設計書
                                </a>

                                <button
                                    onClick={toggleDark}
                                    className="ml-1 p-2 rounded-lg text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                                    title={
                                        isDark ? 'ライトモードに切り替え' : 'ダークモードに切り替え'
                                    }
                                >
                                    {isDark ? (
                                        <Sun className="w-5 h-5" />
                                    ) : (
                                        <Moon className="w-5 h-5" />
                                    )}
                                </button>
                            </nav>
                        </div>
                    </div>
                </header>
            )}
            <main className="flex-1 w-full mx-auto">
                <Outlet />
            </main>
        </div>
    );
}
