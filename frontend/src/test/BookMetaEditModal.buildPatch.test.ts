/**
 * BookMetaEditModal の PATCH payload 組み立てロジックのユニットテスト。
 *
 * 回帰対象バグ: isbn/release_date は BookSummary に含まれないため、モーダルを開いた時点で
 * 常に空文字初期化される。未編集のままこれらを PATCH に含めると、バックエンドは空文字を
 * 「既存値のクリア」と解釈し、ユーザーが触っていない ISBN・発売日を消してしまっていた。
 */
import { describe, it, expect } from 'vitest';
import { buildNovelMetaPatch } from '@/features/novel_db/bookMetaPatch';

const baseParams = {
    authors: '石田 リンネ',
    seriesId: 's1',
    volNum: 3,
    publisher: 'ビーズログ文庫',
    asin: 'B009IMAVXC',
};

describe('buildNovelMetaPatch', () => {
    it('isbn/release_date を触っていない場合は payload から除外する（データ消失防止）', () => {
        const patch = buildNovelMetaPatch({
            ...baseParams,
            isbn: '',
            isbnTouched: false,
            releaseDate: '',
            releaseDateTouched: false,
        });

        expect(patch).not.toHaveProperty('isbn');
        expect(patch).not.toHaveProperty('release_date');
        // 他フィールドは従来通り送信される
        expect(patch.authors).toEqual(['石田 リンネ']);
        expect(patch.series_id).toBe('s1');
        expect(patch.volume).toBe(3);
        expect(patch.publisher).toBe('ビーズログ文庫');
        expect(patch.asin).toBe('B009IMAVXC');
    });

    it('isbn を編集した場合は trim した値を payload に含める', () => {
        const patch = buildNovelMetaPatch({
            ...baseParams,
            isbn: ' 9784047264298 ',
            isbnTouched: true,
            releaseDate: '',
            releaseDateTouched: false,
        });

        expect(patch.isbn).toBe('9784047264298');
        expect(patch).not.toHaveProperty('release_date');
    });

    it('release_date を編集した場合は payload に含める', () => {
        const patch = buildNovelMetaPatch({
            ...baseParams,
            isbn: '',
            isbnTouched: false,
            releaseDate: '2024-01-01',
            releaseDateTouched: true,
        });

        expect(patch).not.toHaveProperty('isbn');
        expect(patch.release_date).toBe('2024-01-01');
    });

    it('編集した上で空にした場合は明示的なクリア意図として空文字を送る', () => {
        const patch = buildNovelMetaPatch({
            ...baseParams,
            isbn: '   ',
            isbnTouched: true,
            releaseDate: '',
            releaseDateTouched: true,
        });

        expect(patch.isbn).toBe('');
        expect(patch.release_date).toBe('');
    });

    it('volume が空なら volume_clear を送る（既存挙動の維持）', () => {
        const patch = buildNovelMetaPatch({
            ...baseParams,
            volNum: null,
            isbn: '',
            isbnTouched: false,
            releaseDate: '',
            releaseDateTouched: false,
        });

        expect(patch.volume_clear).toBe(true);
        expect(patch).not.toHaveProperty('volume');
    });
});
