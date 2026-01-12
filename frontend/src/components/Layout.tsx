import { Link, Outlet, useLocation, useSearchParams } from 'react-router-dom';
import { FileText, Library, Settings, Terminal } from 'lucide-react';

export default function Layout() {
    const location = useLocation();
    const [searchParams] = useSearchParams();
    const isReaderMode = searchParams.has('file');

    const isActive = (path: string) => {
        return location.pathname === path ? "text-blue-600 bg-blue-50" : "text-gray-600 hover:bg-gray-50";
    };

    return (
        <div className="min-h-screen bg-gray-50 flex flex-col font-sans text-gray-900">
            {!isReaderMode && (
                <header className="bg-white border-b border-gray-200 sticky top-0 z-50">
                    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                        <div className="flex justify-between h-16">
                            <div className="flex items-center">
                                <Link to="/" className="flex items-center gap-2">
                                    <div className="bg-blue-600 p-1.5 rounded-lg">
                                        <FileText className="w-6 h-6 text-white" />
                                    </div>
                                    <span className="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-600 to-indigo-600">
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
