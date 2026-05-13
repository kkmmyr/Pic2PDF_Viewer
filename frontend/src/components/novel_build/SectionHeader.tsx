export default function SectionHeader({ title, count }: { title: string; count?: number }) {
    return (
        <h2 className="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-2 flex items-center gap-2">
            {title}
            {count !== undefined && (
                <span className="text-xs font-normal bg-gray-100 dark:bg-gray-800 rounded-full px-2 py-0.5">
                    {count}
                </span>
            )}
        </h2>
    );
}
