import { createBrowserRouter, Navigate } from 'react-router-dom';
import Layout from '@/components/Layout';
import RouteErrorPage from '@/components/RouteErrorPage';
import {
    GeneratorPage,
    HitomiPage,
    KindleCatalogPage,
    NovelDbPage,
    NovelDetailPage,
    NovelDiscussionPage,
    NovelGraphPage,
    NovelManagePage,
    NovelReaderPage,
    ViewerPage,
} from '@/lazyPages';

const err = <RouteErrorPage />;

export const router = createBrowserRouter([
    {
        path: '/',
        element: <Layout />,
        errorElement: <RouteErrorPage />,
        children: [
            { index: true, element: <Navigate to="/doujin" replace /> },
            { path: 'doujin', element: <ViewerPage />, errorElement: err },
            { path: 'doujin/generator', element: <GeneratorPage />, errorElement: err },
            { path: 'doujin/hitomi', element: <HitomiPage />, errorElement: err },
            { path: 'comic', element: <ViewerPage />, errorElement: err },
            { path: 'kindle/catalog', element: <KindleCatalogPage />, errorElement: err },
            { path: 'novel', element: <Navigate to="/novel/db" replace /> },
            { path: 'novel/db', element: <NovelDbPage />, errorElement: err },
            { path: 'novel/manage', element: <NovelManagePage />, errorElement: err },
            { path: 'novel/discussion', element: <NovelDiscussionPage />, errorElement: err },
            { path: 'novel/detail/:bookName', element: <NovelDetailPage />, errorElement: err },
            { path: 'novel/reader/:bookName', element: <NovelReaderPage />, errorElement: err },
            { path: 'novel/graph', element: <NovelGraphPage />, errorElement: err },
        ],
    },
]);
