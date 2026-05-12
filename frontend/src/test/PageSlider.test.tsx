import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import { PageSlider } from '../components/reader/PageSlider';

const renderSlider = (overrides: Partial<Parameters<typeof PageSlider>[0]> = {}) => {
    const props = {
        pageNumber: 1,
        numPages: 10,
        isSpread: false,
        direction: 'ltr' as const,
        show: true,
        selectedPdf: 'book.pdf',
        currentPath: '',
        currentSource: 'doujin' as const,
        onPageJump: vi.fn(),
        ...overrides,
    };
    return { props, ...render(<PageSlider {...props} />) };
};

describe('PageSlider', () => {
    beforeEach(() => {
        vi.useFakeTimers();
    });
    afterEach(() => {
        vi.useRealTimers();
    });

    it('numPages=0 では何もレンダーしない', () => {
        const { container } = renderSlider({ numPages: 0 });
        expect(container.firstChild).toBeNull();
    });

    it('現在ページ表示 P.{n} が出る', () => {
        const { getByText } = renderSlider({ pageNumber: 3, numPages: 10 });
        expect(getByText('P.3')).toBeInTheDocument();
    });

    it('総ページ数 / N が出る', () => {
        const { getByText } = renderSlider({ pageNumber: 1, numPages: 42 });
        expect(getByText('/ 42')).toBeInTheDocument();
    });

    it('range input の min=1 / max=numPages / value=pageNumber', () => {
        const { container } = renderSlider({ pageNumber: 5, numPages: 20 });
        const input = container.querySelector('input[type="range"]') as HTMLInputElement;
        expect(input.min).toBe('1');
        expect(input.max).toBe('20');
        expect(input.value).toBe('5');
    });

    it('onPointerUp で値が onPageJump に渡る', () => {
        const onPageJump = vi.fn();
        const { container } = renderSlider({ onPageJump, numPages: 10 });
        const input = container.querySelector('input[type="range"]') as HTMLInputElement;

        // ドラッグして値を変える
        fireEvent.change(input, { target: { value: '7' } });
        fireEvent.pointerUp(input, { target: { value: '7' } });

        expect(onPageJump).toHaveBeenCalledWith(7);
    });

    it('LTR spread モードで偶数値は最寄りの奇数（左ページ境界）に正規化される', () => {
        const onPageJump = vi.fn();
        const { container } = renderSlider({
            isSpread: true,
            direction: 'ltr',
            numPages: 10,
            onPageJump,
        });
        const input = container.querySelector('input[type="range"]') as HTMLInputElement;
        fireEvent.change(input, { target: { value: '4' } });
        fireEvent.pointerUp(input, { target: { value: '4' } });
        // 4 は偶数 → max(1, 4-1) = 3
        expect(onPageJump).toHaveBeenCalledWith(3);
    });

    it('RTL spread モードで奇数値は偶数（左ページ境界）に正規化される（page>1）', () => {
        const onPageJump = vi.fn();
        const { container } = renderSlider({
            isSpread: true,
            direction: 'rtl',
            numPages: 10,
            onPageJump,
        });
        const input = container.querySelector('input[type="range"]') as HTMLInputElement;
        fireEvent.change(input, { target: { value: '5' } });
        fireEvent.pointerUp(input, { target: { value: '5' } });
        // 5 は奇数 → 5-1=4
        expect(onPageJump).toHaveBeenCalledWith(4);
    });

    it('RTL spread の page=1 はそのまま 1（表紙）', () => {
        const onPageJump = vi.fn();
        const { container } = renderSlider({
            isSpread: true,
            direction: 'rtl',
            numPages: 10,
            onPageJump,
        });
        const input = container.querySelector('input[type="range"]') as HTMLInputElement;
        fireEvent.change(input, { target: { value: '1' } });
        fireEvent.pointerUp(input, { target: { value: '1' } });
        expect(onPageJump).toHaveBeenCalledWith(1);
    });

    it('値が範囲外でも clamp される（max 超え）', () => {
        const onPageJump = vi.fn();
        const { container } = renderSlider({ numPages: 10, onPageJump });
        const input = container.querySelector('input[type="range"]') as HTMLInputElement;
        fireEvent.pointerUp(input, { target: { value: '100' } });
        expect(onPageJump).toHaveBeenCalledWith(10);
    });

    it('値が範囲外でも clamp される（min 未満）', () => {
        const onPageJump = vi.fn();
        const { container } = renderSlider({ numPages: 10, onPageJump });
        const input = container.querySelector('input[type="range"]') as HTMLInputElement;
        fireEvent.pointerUp(input, { target: { value: '0' } });
        expect(onPageJump).toHaveBeenCalledWith(1);
    });

    it('show=false で translate-y-full クラスが付き、show=true で translate-y-0', () => {
        const { container, rerender } = render(
            <PageSlider
                pageNumber={1}
                numPages={10}
                isSpread={false}
                direction="ltr"
                show={false}
                selectedPdf="x.pdf"
                currentPath=""
                currentSource="generated"
                onPageJump={vi.fn()}
            />,
        );
        expect((container.firstChild as HTMLElement).className).toContain('translate-y-full');

        rerender(
            <PageSlider
                pageNumber={1}
                numPages={10}
                isSpread={false}
                direction="ltr"
                show
                selectedPdf="x.pdf"
                currentPath=""
                currentSource="generated"
                onPageJump={vi.fn()}
            />,
        );
        expect((container.firstChild as HTMLElement).className).toContain('translate-y-0');
    });
});
