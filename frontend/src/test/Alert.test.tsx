/**
 * Alert コンポーネントの動作テスト。
 *
 * 実行方法:
 *   cd frontend && npx vitest run src/test/Alert.test.tsx
 */
import { render } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { Alert } from '../components/ui/Alert';

describe('Alert', () => {
    it('variant=error は bg-red-50 と AlertCircle アイコン', () => {
        const { container, getByText } = render(<Alert variant="error">エラー</Alert>);
        const root = container.firstChild as HTMLElement;
        expect(root.className).toContain('bg-red-50');
        expect(getByText('エラー')).toBeInTheDocument();
        // 既定アイコンが描画されている（svg として存在）
        expect(root.querySelector('svg')).not.toBeNull();
    });

    it('variant=success は bg-green-50', () => {
        const { container } = render(<Alert variant="success">完了</Alert>);
        expect((container.firstChild as HTMLElement).className).toContain('bg-green-50');
    });

    it('variant=warning は bg-amber-50', () => {
        const { container } = render(<Alert variant="warning">注意</Alert>);
        expect((container.firstChild as HTMLElement).className).toContain('bg-amber-50');
    });

    it('variant=info は bg-primary-50', () => {
        const { container } = render(<Alert variant="info">情報</Alert>);
        expect((container.firstChild as HTMLElement).className).toContain('bg-primary-50');
    });

    it('showIcon=false のときアイコン svg なし', () => {
        const { container } = render(<Alert variant="error" showIcon={false}>x</Alert>);
        expect((container.firstChild as HTMLElement).querySelector('svg')).toBeNull();
    });

    it('icon プロップで既定アイコンを上書きできる', () => {
        const customIcon = <span data-testid="custom-icon" />;
        const { getByTestId, container } = render(
            <Alert variant="error" icon={customIcon}>x</Alert>
        );
        expect(getByTestId('custom-icon')).toBeInTheDocument();
        // 既定の AlertCircle svg は描画されていない
        expect((container.firstChild as HTMLElement).querySelector('svg')).toBeNull();
    });

    it('className が末尾に結合される', () => {
        const { container } = render(<Alert variant="error" className="mt-3 p-4">x</Alert>);
        const cls = (container.firstChild as HTMLElement).className;
        expect(cls).toContain('mt-3');
        expect(cls).toContain('p-4');
    });

    it('error は role="alert" を持つ', () => {
        const { container } = render(<Alert variant="error">x</Alert>);
        expect((container.firstChild as HTMLElement).getAttribute('role')).toBe('alert');
    });

    it('error 以外は role="status"', () => {
        const { container } = render(<Alert variant="success">x</Alert>);
        expect((container.firstChild as HTMLElement).getAttribute('role')).toBe('status');
    });
});
