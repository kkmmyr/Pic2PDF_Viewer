import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';

// react-pdf は pdfjs を import するだけで DOMMatrix を要求する → mock で回避。
// 本テストは画像モード分岐 + End プレースホルダ条件のみを検証するため、
// <Page> 自体は data-testid で観察できるダミー要素にする。
vi.mock('react-pdf', () => ({
    pdfjs: { GlobalWorkerOptions: { workerSrc: '' } },
    Page: ({ pageNumber }: { pageNumber: number }) => (
        <div data-testid="pdf-page">{`pdf-page-${pageNumber}`}</div>
    ),
    Document: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

import { PageRenderer } from '../components/reader/PageRenderer';

const renderPR = (overrides: Partial<Parameters<typeof PageRenderer>[0]> = {}) => {
    const props = {
        pageNumber: 1,
        numPages: 10,
        windowHeight: 800,
        side: 'single' as const,
        direction: 'ltr' as const,
        onNext: vi.fn(),
        onPrev: vi.fn(),
        isSpread: false,
        ...overrides,
    };
    return { props, ...render(<PageRenderer {...props} />) };
};

describe('PageRenderer', () => {
    describe('End プレースホルダ', () => {
        it('pageNumber > numPages の場合は End を表示する', () => {
            const { getByText, queryByTestId } = renderPR({ pageNumber: 11, numPages: 10 });
            expect(getByText('End')).toBeInTheDocument();
            expect(queryByTestId('pdf-page')).toBeNull();
        });

        it('isImageMode かつ imageUrl が undefined の場合は End を表示する（削除直後の transient 防御）', () => {
            const { getByText, queryByTestId } = renderPR({
                pageNumber: 5,
                numPages: 10,
                isImageMode: true,
                imageUrl: undefined,
            });
            expect(getByText('End')).toBeInTheDocument();
            // PDF 経路に倒れて <Page> が描画されないことを確認
            expect(queryByTestId('pdf-page')).toBeNull();
        });

        it('isImageMode かつ imageUrl が null の場合も End を表示する', () => {
            const { getByText } = renderPR({
                pageNumber: 5,
                numPages: 10,
                isImageMode: true,
                imageUrl: null,
            });
            expect(getByText('End')).toBeInTheDocument();
        });
    });

    describe('画像モード', () => {
        it('isImageMode かつ imageUrl があれば <img> を描画する', () => {
            const { container } = renderPR({
                isImageMode: true,
                imageUrl: '/images/book/01.webp',
            });
            const img = container.querySelector('img');
            expect(img).not.toBeNull();
            expect(img?.getAttribute('src')).toContain('/images/book/01.webp');
        });
    });

    describe('PDF モード', () => {
        it('isImageMode=false なら <Page> を描画する', () => {
            const { getByTestId, container } = renderPR({ isImageMode: false });
            expect(getByTestId('pdf-page')).toBeInTheDocument();
            expect(container.querySelector('img')).toBeNull();
        });
    });
});
