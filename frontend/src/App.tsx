import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { lazy, Suspense } from 'react';
import Layout from './components/Layout';
import ErrorBoundary from './components/ErrorBoundary';
import GeneratorPage from './pages/GeneratorPage';
import ViewerPage from './pages/ViewerPage';
import HitomiPage from './pages/HitomiPage';
import NovelDbPage from './pages/NovelDbPage';
import NovelManagePage from './pages/NovelManagePage';
import NovelDetailPage from './pages/NovelDetailPage';
import NovelDiscussionPage from './pages/NovelDiscussionPage';
import NovelReaderPage from './pages/NovelReaderPage';

// vis-network を含む重いページは遅延ロード
const NovelGraphPage = lazy(() => import('./pages/NovelGraphPage'));

function App() {
    return (
        <BrowserRouter>
            <ErrorBoundary>
                <Routes>
                    <Route path="/" element={<Layout />}>
                        <Route index element={<Navigate to="/doujin" replace />} />
                        <Route
                            path="doujin"
                            element={
                                <ErrorBoundary>
                                    <ViewerPage />
                                </ErrorBoundary>
                            }
                        />
                        <Route
                            path="doujin/generator"
                            element={
                                <ErrorBoundary>
                                    <GeneratorPage />
                                </ErrorBoundary>
                            }
                        />
                        <Route
                            path="doujin/hitomi"
                            element={
                                <ErrorBoundary>
                                    <HitomiPage />
                                </ErrorBoundary>
                            }
                        />
                        <Route
                            path="comic"
                            element={
                                <ErrorBoundary>
                                    <ViewerPage />
                                </ErrorBoundary>
                            }
                        />
                        <Route path="novel" element={<Navigate to="/novel/db" replace />} />
                        <Route
                            path="novel/db"
                            element={
                                <ErrorBoundary>
                                    <NovelDbPage />
                                </ErrorBoundary>
                            }
                        />
                        <Route
                            path="novel/manage"
                            element={
                                <ErrorBoundary>
                                    <NovelManagePage />
                                </ErrorBoundary>
                            }
                        />
                        <Route
                            path="novel/discussion"
                            element={
                                <ErrorBoundary>
                                    <NovelDiscussionPage />
                                </ErrorBoundary>
                            }
                        />
                        <Route
                            path="novel/detail/:bookName"
                            element={
                                <ErrorBoundary>
                                    <NovelDetailPage />
                                </ErrorBoundary>
                            }
                        />
                        <Route
                            path="novel/reader/:bookName"
                            element={
                                <ErrorBoundary>
                                    <NovelReaderPage />
                                </ErrorBoundary>
                            }
                        />
                        <Route
                            path="novel/graph"
                            element={
                                <ErrorBoundary>
                                    <Suspense fallback={null}>
                                        <NovelGraphPage />
                                    </Suspense>
                                </ErrorBoundary>
                            }
                        />
                    </Route>
                </Routes>
            </ErrorBoundary>
        </BrowserRouter>
    );
}

export default App;
