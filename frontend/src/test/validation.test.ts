import { describe, it, expect } from 'vitest';
import { validateFilename } from '@/utils/validation';

describe('validateFilename', () => {
    describe('空入力', () => {
        it('空文字でファイル用エラー', () => {
            expect(validateFilename('', 'file')).toBe('ファイル名を入力してください。');
        });

        it('空文字でフォルダ用エラー', () => {
            expect(validateFilename('', 'folder')).toBe('フォルダ名を入力してください。');
        });

        it('空白のみは空入力扱い', () => {
            expect(validateFilename('   ', 'file')).toBe('ファイル名を入力してください。');
        });

        it('タブのみも空入力扱い', () => {
            expect(validateFilename('\t', 'file')).toBe('ファイル名を入力してください。');
        });
    });

    describe('不正文字', () => {
        it.each([['/'], ['\\'], [':'], ['*'], ['?'], ['"'], ['<'], ['>'], ['|']])(
            '"%s" を含むとエラー',
            (char) => {
                const msg = validateFilename(`name${char}.pdf`, 'file');
                expect(msg).toMatch(/使用できない文字/);
            },
        );

        it('複数の不正文字を含むケースもエラー', () => {
            expect(validateFilename('a/b\\c.pdf', 'file')).toMatch(/使用できない文字/);
        });

        it('フォルダ用でも同じ判定', () => {
            expect(validateFilename('Sub/Folder', 'folder')).toMatch(/使用できない文字/);
        });
    });

    describe('正常入力', () => {
        it('日本語ファイル名は OK（null）', () => {
            expect(validateFilename('書籍.pdf', 'file')).toBeNull();
        });

        it('英数字 + ハイフン + 拡張子は OK', () => {
            expect(validateFilename('book-01.pdf', 'file')).toBeNull();
        });

        it('スペースを含む名前は OK（不正文字ではない）', () => {
            expect(validateFilename('my book.pdf', 'file')).toBeNull();
        });

        it('ドットを含む名前は OK', () => {
            expect(validateFilename('a.b.c.pdf', 'file')).toBeNull();
        });

        it('フォルダ名も同じ判定', () => {
            expect(validateFilename('Sub Folder', 'folder')).toBeNull();
        });
    });
});
