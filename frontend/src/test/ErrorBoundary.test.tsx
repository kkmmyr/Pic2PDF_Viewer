import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import ErrorBoundary from '../components/ErrorBoundary';

const ThrowingChild = ({ msg }: { msg: string }) => {
    throw new Error(msg);
};

// jsdom はエラーバウンダリ内で起きた throw を window 'error' イベントで再発火するため、
// テスト出力に大量のスタックトレースが出る。preventDefault で抑制する。
const swallowError = (e: Event) => e.preventDefault();

describe('ErrorBoundary', () => {
    let errSpy: ReturnType<typeof vi.spyOn>;

    beforeEach(() => {
        // React は エラーバウンダリ起動時に console.error を出す → テスト出力をクリーンに保つ
        errSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
        window.addEventListener('error', swallowError);
    });

    afterEach(() => {
        errSpy.mockRestore();
        window.removeEventListener('error', swallowError);
    });

    it('正常な子はそのまま描画する', () => {
        const { getByText } = render(
            <ErrorBoundary>
                <div>正常な子</div>
            </ErrorBoundary>,
        );
        expect(getByText('正常な子')).toBeInTheDocument();
    });

    it('子で例外が発生すると fallback が表示され、message も含まれる', () => {
        const { getByText } = render(
            <ErrorBoundary>
                <ThrowingChild msg="boom!" />
            </ErrorBoundary>,
        );
        expect(getByText('エラーが発生しました')).toBeInTheDocument();
        expect(getByText('boom!')).toBeInTheDocument();
    });

    it('「再読み込み」ボタンが表示される', () => {
        const { getByText } = render(
            <ErrorBoundary>
                <ThrowingChild msg="x" />
            </ErrorBoundary>,
        );
        expect(getByText('再読み込み')).toBeInTheDocument();
    });

    it('再読み込みボタンクリックで window.location.reload が呼ばれる', () => {
        const reloadMock = vi.fn();
        const original = window.location;
        Object.defineProperty(window, 'location', {
            configurable: true,
            value: { ...window.location, reload: reloadMock },
        });

        const { getByText } = render(
            <ErrorBoundary>
                <ThrowingChild msg="x" />
            </ErrorBoundary>,
        );
        fireEvent.click(getByText('再読み込み'));
        expect(reloadMock).toHaveBeenCalled();

        Object.defineProperty(window, 'location', { configurable: true, value: original });
    });
});
