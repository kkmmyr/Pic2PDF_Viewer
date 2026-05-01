interface EdgeHoverZonesProps {
    onEnterTop: () => void;
    onEnterBottom: () => void;
}

export function EdgeHoverZones({ onEnterTop, onEnterBottom }: EdgeHoverZonesProps) {
    return (
        <>
            {/* ヘッダー表示トリガーゾーン: ヘッダー (h-14) と高さを揃える */}
            <div
                className="fixed top-0 left-0 right-0 h-14 z-overlay-bar"
                onMouseEnter={onEnterTop}
            />
            {/* スライダー表示トリガーゾーン: スライダー (h-12) と高さを揃える */}
            <div
                className="fixed bottom-0 left-0 right-0 h-12 z-overlay-bar"
                onMouseEnter={onEnterBottom}
            />
        </>
    );
}
