import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import ErrorBoundary from './components/ErrorBoundary';
import GeneratorPage from './pages/GeneratorPage';
import ViewerPage from './pages/ViewerPage';
import OCRPage from './pages/OCRPage';

function App() {
    return (
        <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
            <ErrorBoundary>
                <Routes>
                    <Route path="/" element={<Layout />}>
                        <Route index element={<Navigate to="/viewer" replace />} />
                        <Route path="viewer" element={
                            <ErrorBoundary>
                                <ViewerPage />
                            </ErrorBoundary>
                        } />
                        <Route path="generator" element={
                            <ErrorBoundary>
                                <GeneratorPage />
                            </ErrorBoundary>
                        } />
                        <Route path="ocr" element={
                            <ErrorBoundary>
                                <OCRPage />
                            </ErrorBoundary>
                        } />
                    </Route>
                </Routes>
            </ErrorBoundary>
        </BrowserRouter>
    );
}

export default App;
