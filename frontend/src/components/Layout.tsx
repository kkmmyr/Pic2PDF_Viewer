import { Link, Outlet, useLocation, useSearchParams } from 'react-router-dom';
import {
    FileText,
    Library,
    Settings,
    Terminal,
    Moon,
    Sun,
    Sparkles,
    BookOpen,
    BookText,
} from 'lucide-react';
import { useDarkMode } from '../hooks';

export default function Layout() {
    const location = useLocation();
    const [searchParams] = useSearchParams();
    const isReaderMode = searchParams.has('file');
    const { isDark, toggle: toggleDark } = useDarkMode();

    const isActive = (path: string) => {
        return location.pathname === path
            ? 'text-primary-600 bg-primary-50 dark:text-primary-400 dark:bg-primary-900/30'
            : 'text-gray-600 hover:bg-gray-50 dark:text-gray-400 dark:hover:bg-gray-800';
    };

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
                                {/* 同人誌 */}
                                <span className="text-xs text-gray-400 dark:text-gray-500 px-1.5 select-none">
                                    同人誌
                                </span>
                                <Link
                                    to="/doujin"
                                    className={`px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200 flex items-center gap-1.5 ${isActive('/doujin')}`}
                                >
                                    <Library className="w-4 h-4" />
                                    Library
                                </Link>
                                <Link
                                    to="/doujin/generator"
                                    className={`px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200 flex items-center gap-1.5 ${isActive('/doujin/generator')}`}
                                >
                                    <Settings className="w-4 h-4" />
                                    Generator
                                </Link>
                                <Link
                                    to="/doujin/hitomi"
                                    className={`px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200 flex items-center gap-1.5 ${isActive('/doujin/hitomi')}`}
                                >
                                    <Sparkles className="w-4 h-4" />
                                    新着
                                </Link>

                                <div className="w-px h-5 bg-gray-200 dark:bg-gray-700 mx-1" />

                                {/* 漫画 */}
                                <span className="text-xs text-gray-400 dark:text-gray-500 px-1.5 select-none">
                                    漫画
                                </span>
                                <Link
                                    to="/comic"
                                    className={`px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200 flex items-center gap-1.5 ${isActive('/comic')}`}
                                >
                                    <Library className="w-4 h-4" />
                                    Library
                                </Link>

                                <div className="w-px h-5 bg-gray-200 dark:bg-gray-700 mx-1" />

                                {/* 小説 */}
                                <span className="text-xs text-gray-400 dark:text-gray-500 px-1.5 select-none">
                                    小説
                                </span>
                                <Link
                                    to="/novel/db"
                                    className={`px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200 flex items-center gap-1.5 ${isActive('/novel/db')}`}
                                >
                                    <BookOpen className="w-4 h-4" />
                                    DB
                                </Link>
                                <Link
                                    to="/novel/ocr"
                                    className={`px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200 flex items-center gap-1.5 ${isActive('/novel/ocr')}`}
                                >
                                    <Terminal className="w-4 h-4" />
                                    OCR
                                </Link>

                                <div className="w-px h-5 bg-gray-200 dark:bg-gray-700 mx-1" />

                                <a
                                    href="/site/index.html"
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200 flex items-center gap-1.5 text-gray-600 hover:bg-gray-50 dark:text-gray-400 dark:hover:bg-gray-800"
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
