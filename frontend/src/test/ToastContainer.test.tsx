import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import { ToastContainer } from '../components/reader/ToastContainer';
import type { Toast } from '../hooks/useToast';

const t = (id: number, message: string, type: Toast['type'] = 'info'): Toast => ({
    id,
    message,
    type,
});

describe('ToastContainer', () => {
    it('toasts が空なら何もレンダーしない', () => {
        const { container } = render(<ToastContainer toasts={[]} onDismiss={vi.fn()} />);
        expect(container.firstChild).toBeNull();
    });

    it('toast を message とともに描画', () => {
        const { getByText } = render(
            <ToastContainer toasts={[t(1, '保存しました', 'success')]} onDismiss={vi.fn()} />,
        );
        expect(getByText('保存しました')).toBeInTheDocument();
    });

    it('複数の toast を順番に描画', () => {
        const { getByText } = render(
            <ToastContainer toasts={[t(1, 'A', 'info'), t(2, 'B', 'error')]} onDismiss={vi.fn()} />,
        );
        expect(getByText('A')).toBeInTheDocument();
        expect(getByText('B')).toBeInTheDocument();
    });

    it('type=success で bg-green-600 が付く', () => {
        const { container } = render(
            <ToastContainer toasts={[t(1, 'ok', 'success')]} onDismiss={vi.fn()} />,
        );
        const toastEl = container.querySelector('.bg-green-600');
        expect(toastEl).not.toBeNull();
    });

    it('type=error で bg-red-600 が付く', () => {
        const { container } = render(
            <ToastContainer toasts={[t(1, 'ng', 'error')]} onDismiss={vi.fn()} />,
        );
        expect(container.querySelector('.bg-red-600')).not.toBeNull();
    });

    it('type=info で bg-gray-800 が付く', () => {
        const { container } = render(
            <ToastContainer toasts={[t(1, 'i', 'info')]} onDismiss={vi.fn()} />,
        );
        expect(container.querySelector('.bg-gray-800')).not.toBeNull();
    });

    it('×ボタンクリックで onDismiss(id) が呼ばれる', () => {
        const onDismiss = vi.fn();
        const { container } = render(
            <ToastContainer toasts={[t(7, 'x', 'info')]} onDismiss={onDismiss} />,
        );
        const dismissBtn = container.querySelector('button')!;
        fireEvent.click(dismissBtn);
        expect(onDismiss).toHaveBeenCalledWith(7);
    });
});
