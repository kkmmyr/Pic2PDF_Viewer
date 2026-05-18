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
            {/* ヘッダー表示トリガー: iOS セーフエリア下端から始まる */}
            <div
                className="fixed left-0 right-0 z-overlay-bar"
                style={{
                    top: 'env(safe-area-inset-top, 0px)',
                    height: 'calc(3.5rem + env(safe-area-inset-top, 0px))',
                }}
                onMouseEnter={onEnterTop}
                onTouchStart={onTouchTop}
            />
            {/* スライダー表示トリガー: iOS ホームジェスチャーエリアから 16px 離す */}
            <div
                className="fixed left-0 right-0 z-overlay-bar"
                style={{
                    bottom: 'calc(env(safe-area-inset-bottom, 20px) + 16px)',
                    height: '3.5rem',
                }}
                onMouseEnter={onEnterBottom}
                onTouchStart={onTouchBottom}
            />
        </>
    );
}
