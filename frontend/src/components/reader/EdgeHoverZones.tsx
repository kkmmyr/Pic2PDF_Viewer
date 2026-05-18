interface EdgeHoverZonesProps {
    onEnterTop: () => void;
    onEnterBottom: () => void;
    onTouchTop?: () => void;
    onTouchBottom?: () => void;
}

export function EdgeHoverZones({
    onEnterTop,
    onEnterBottom,
    onTouchTop,
    onTouchBottom,
}: EdgeHoverZonesProps) {
    return (
        <>
            {/* ヘッダー表示トリガー: 画面上端から始め safe-area + 4rem の高さ */}
            <div
                className="fixed left-0 right-0 z-overlay-bar"
                style={{
                    top: 0,
                    height: 'calc(env(safe-area-inset-top, 0px) + 4rem)',
                }}
                onMouseEnter={onEnterTop}
                onTouchStart={onTouchTop}
            />
            {/* スライダー表示トリガー: 画面下端から始め safe-area + 3.5rem の高さ */}
            <div
                className="fixed left-0 right-0 z-overlay-bar"
                style={{
                    bottom: 0,
                    height: 'calc(env(safe-area-inset-bottom, 0px) + 3.5rem)',
                }}
                onMouseEnter={onEnterBottom}
                onTouchStart={onTouchBottom}
            />
        </>
    );
}
