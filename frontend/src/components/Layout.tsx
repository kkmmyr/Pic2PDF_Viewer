import { Link, Outlet, useLocation, useSearchParams } from 'react-router-dom';
import { FileText, Library, Settings, Terminal, Moon, Sun, Sparkles, BookOpen } from 'lucide-react';
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

                            <nav className="flex items-center gap-1">
                                <Link
                                    to="/viewer"
                                    className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 flex items-center gap-2 ${isActive('/viewer')}`}
                                >
                                    <Library className="w-4 h-4" />
                                    Library
                                </Link>
                                <Link
                                    to="/generator"
                                    className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 flex items-center gap-2 ${isActive('/generator')}`}
                                >
                                    <Settings className="w-4 h-4" />
                                    Generator
                                </Link>
                                <Link
                                    to="/ocr"
                                    className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 flex items-center gap-2 ${isActive('/ocr')}`}
                                >
                                    <Terminal className="w-4 h-4" />
                                    Novel OCR
                                </Link>
                                <Link
                                    to="/hitomi"
                                    className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 flex items-center gap-2 ${isActive('/hitomi')}`}
                                >
                                    <Sparkles className="w-4 h-4" />
                                    新着
                                </Link>
                                <Link
                                    to="/novel-db"
                                    className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 flex items-center gap-2 ${isActive('/novel-db')}`}
                                >
                                    <BookOpen className="w-4 h-4" />
                                    小説検索
                                </Link>

                                {/* ダークモード切り替えボタン */}
                                <button
                                    onClick={toggleDark}
                                    className="ml-2 p-2 rounded-lg text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
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
