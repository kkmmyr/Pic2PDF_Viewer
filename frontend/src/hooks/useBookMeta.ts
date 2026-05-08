import { useBookMetaCore } from './useBookMetaCore';
import { useBookMetaWrite } from './useBookMetaWrite';
import { useBookSeries } from './useBookSeries';
import { useBookView } from './useBookView';
import { useMetaDerived } from './useMetaDerived';

/**
 * 書籍メタデータ（作者名 / ジャンル / 非表示 / シリーズ / 閲覧履歴 / 読書状態）を
 * 管理する合成フック。
 *
 * 責務別の 4 フックに分離されており、本フックはそれらを合成して既存 API
 * （getter 群 + updateAuthors / updateGenre / setHidden /
 * assignSeries / unassignSeries / reorderSeries / recordView /
 * 派生集計 + refreshMeta）を維持する。
 */
export function useBookMeta(source: string) {
    const core = useBookMetaCore(source);
    const write = useBookMetaWrite(source, core.setMeta, core.makeKey);
    const series = useBookSeries(source, core.setMeta, core.makeKey);
    const view = useBookView(source, core.setMeta, core.makeKey);
    const derived = useMetaDerived(core.meta);

    return {
        meta: core.meta,
        getAuthors: core.getAuthors,
        getSeries: core.getSeries,
        isHidden: core.isHidden,
        getViewCount: core.getViewCount,
        getLastViewedAt: core.getLastViewedAt,
        getReadState: core.getReadState,
        recordView: view.recordView,
        updateAuthors: write.updateAuthors,
        updateMeta: write.updateMeta,
        updateGenre: write.updateGenre,
        setHidden: write.setHidden,
        setReadState: write.setReadState,
        assignSeries: series.assignSeries,
        unassignSeries: series.unassignSeries,
        reorderSeries: series.reorderSeries,
        ...derived,
        refreshMeta: core.fetchMeta,
    };
}
