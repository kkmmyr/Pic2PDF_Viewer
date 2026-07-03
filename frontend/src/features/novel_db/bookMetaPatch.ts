/**
 * BookMetaEditModal（4.3）の PATCH payload 組み立てロジック。
 * コンポーネントファイルから切り出し、ユニットテスト可能にしている。
 */
import type { NovelMetaPatch } from './types';

function splitAuthors(raw: string): string[] {
    return raw
        .split(/[,、]/)
        .map((s) => s.trim())
        .filter(Boolean);
}

interface BuildNovelMetaPatchParams {
    authors: string;
    seriesId: string;
    volNum: number | null;
    publisher: string;
    asin: string;
    isbn: string;
    isbnTouched: boolean;
    releaseDate: string;
    releaseDateTouched: boolean;
}

/**
 * PATCH payload を組み立てる。
 *
 * isbn/release_date は `BookSummary` に含まれないフィールドのため、モーダルを開いた
 * 時点では常に空文字で初期化される。未編集のままこれらを PATCH に含めると、バックエンド
 * （backend/routers/meta/novel.py）は空文字を「既存値のクリア」と解釈してしまい、
 * ユーザーが触っていない ISBN・発売日が保存のたびに消えてしまう（実データ破壊バグ）。
 * そのため、ユーザーが実際に入力欄を編集した（*Touched === true）場合のみ payload に含める。
 */
export function buildNovelMetaPatch({
    authors,
    seriesId,
    volNum,
    publisher,
    asin,
    isbn,
    isbnTouched,
    releaseDate,
    releaseDateTouched,
}: BuildNovelMetaPatchParams): NovelMetaPatch {
    return {
        authors: splitAuthors(authors),
        series_id: seriesId.trim(),
        ...(volNum != null ? { volume: volNum } : { volume_clear: true }),
        publisher: publisher.trim(),
        asin: asin.trim(),
        ...(isbnTouched ? { isbn: isbn.trim() } : {}),
        ...(releaseDateTouched ? { release_date: releaseDate.trim() } : {}),
    };
}
