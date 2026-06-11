/**
 * Button コンポーネントの基本動作テスト。
 *
 * 実行方法:
 *   cd frontend && npx vitest run src/test/Button.test.tsx
 */
import { render, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { createRef } from 'react';
import { Button } from '@/components/ui/Button';

describe('Button', () => {
    it('既定で variant=primary, size=md の class が付く', () => {
        const { getByRole } = render(<Button>OK</Button>);
        const btn = getByRole('button');
        expect(btn.className).toContain('bg-primary-600');
        expect(btn.className).toContain('px-3');
        expect(btn.className).toContain('py-1.5');
        expect(btn.className).toContain('text-sm');
    });

    it('variant=danger は bg-red-600 が付く', () => {
        const { getByRole } = render(<Button variant="danger">削除</Button>);
        expect(getByRole('button').className).toContain('bg-red-600');
    });

    it('variant=secondary は bg-gray-100 が付く', () => {
        const { getByRole } = render(<Button variant="secondary">キャンセル</Button>);
        expect(getByRole('button').className).toContain('bg-gray-100');
    });

    it('variant=ghost は bg-transparent が付く', () => {
        const { getByRole } = render(<Button variant="ghost">×</Button>);
        expect(getByRole('button').className).toContain('bg-transparent');
    });

    it('size=lg は px-6 py-3 text-base が付く', () => {
        const { getByRole } = render(<Button size="lg">生成</Button>);
        const cls = getByRole('button').className;
        expect(cls).toContain('px-6');
        expect(cls).toContain('py-3');
        expect(cls).toContain('text-base');
    });

    it('disabled の時 onClick は呼ばれない', () => {
        const onClick = vi.fn();
        const { getByRole } = render(
            <Button disabled onClick={onClick}>
                OK
            </Button>,
        );
        fireEvent.click(getByRole('button'));
        expect(onClick).not.toHaveBeenCalled();
    });

    it('通常時 onClick が呼ばれる', () => {
        const onClick = vi.fn();
        const { getByRole } = render(<Button onClick={onClick}>OK</Button>);
        fireEvent.click(getByRole('button'));
        expect(onClick).toHaveBeenCalledTimes(1);
    });

    it('追加 className が末尾に結合される', () => {
        const { getByRole } = render(<Button className="ml-4">OK</Button>);
        expect(getByRole('button').className).toMatch(/ml-4$/);
    });

    it('既定の type は "button"（form submit を防ぐ）', () => {
        const { getByRole } = render(<Button>OK</Button>);
        expect(getByRole('button').getAttribute('type')).toBe('button');
    });

    it('forwardRef で button 要素にアクセスできる', () => {
        const ref = createRef<HTMLButtonElement>();
        render(<Button ref={ref}>OK</Button>);
        expect(ref.current).toBeInstanceOf(HTMLButtonElement);
    });
});
