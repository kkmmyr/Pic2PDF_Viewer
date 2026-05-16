/**
 * C-12: vis-network を使ったキャラクタ関係グラフ描画コンポーネント。
 */
import { useEffect, useRef } from 'react';
import { Network, type Options } from 'vis-network';
import type { GraphData } from '../../features/novel_graph/api';

interface Props {
    data: GraphData;
    /** ノードクリック時にキャラ名を通知 */
    onNodeClick?: (label: string) => void;
}

const NETWORK_OPTIONS: Options = {
    nodes: {
        shape: 'dot',
        size: 16,
        font: { size: 14 },
        borderWidth: 2,
        color: { background: '#6366f1', border: '#4f46e5', highlight: { background: '#818cf8', border: '#6366f1' } },
    },
    edges: {
        font: { size: 11, align: 'middle' },
        color: { color: '#94a3b8', highlight: '#6366f1' },
        smooth: { enabled: true, type: 'dynamic', roundness: 0.5 },
        width: 1.5,
        scaling: { min: 1, max: 6 },
    },
    physics: {
        stabilization: { iterations: 150 },
        barnesHut: { gravitationalConstant: -8000, springLength: 120 },
    },
    interaction: { tooltipDelay: 100, hideEdgesOnDrag: true },
};

export default function CharacterGraph({ data, onNodeClick }: Props) {
    const containerRef = useRef<HTMLDivElement>(null);
    const networkRef = useRef<Network | null>(null);

    useEffect(() => {
        if (!containerRef.current) return;

        const nodes = data.nodes.map((n) => ({ id: n.id, label: n.label }));
        const edges = data.edges.map((e) => ({
            id: e.id,
            from: e.from,
            to: e.to,
            label: e.label || undefined,
            // 共起回数をエッジ太さに反映（1〜10 の範囲にクランプ）
            width: Math.min(Math.max(e.weight, 1), 10),
        }));

        networkRef.current = new Network(
            containerRef.current,
            { nodes, edges },
            NETWORK_OPTIONS,
        );

        if (onNodeClick) {
            networkRef.current.on('click', (params) => {
                if (params.nodes.length > 0) {
                    const nodeId = params.nodes[0] as number;
                    const node = data.nodes.find((n) => n.id === nodeId);
                    if (node) onNodeClick(node.label);
                }
            });
        }

        return () => {
            networkRef.current?.destroy();
            networkRef.current = null;
        };
    }, [data, onNodeClick]);

    return <div ref={containerRef} className="w-full h-full" />;
}
