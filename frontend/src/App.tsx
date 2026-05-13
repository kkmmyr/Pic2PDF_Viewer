import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import ErrorBoundary from './components/ErrorBoundary';
import GeneratorPage from './pages/GeneratorPage';
import ViewerPage from './pages/ViewerPage';
import OCRPage from './pages/OCRPage';
import HitomiPage from './pages/HitomiPage';
import NovelDbPage from './pages/NovelDbPage';
import NovelBuildPage from './pages/NovelBuildPage';
import NovelDetailPage from './pages/NovelDetailPage';
import NovelDiscussionPage from './pages/NovelDiscussionPage';
import NovelReaderPage from './pages/NovelReaderPage';

function App() {
    return (
        <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
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
                            path="novel/ocr"
                            element={
                                <ErrorBoundary>
                                    <OCRPage />
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
                            path="novel/build"
                            element={
                                <ErrorBoundary>
                                    <NovelBuildPage />
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
