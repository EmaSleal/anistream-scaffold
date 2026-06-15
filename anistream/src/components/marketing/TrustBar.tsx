import styles from "./TrustBar.module.css";

interface TrustBarProps {
  seriesCount: number;
}

interface Tile {
  value: string;
  label: string;
}

export function TrustBar({ seriesCount }: TrustBarProps) {
  const displayCount = seriesCount > 0 ? seriesCount : 1000;

  const tiles: Tile[] = [
    { value: `${displayCount}+`, label: "Series" },
    { value: "Sub & Dub", label: "Audio tracks for every title" },
    { value: "Day-0", label: "Simulcasts from Japan" },
    { value: "Free", label: "No subscription, ever" },
  ];

  return (
    <div className={styles.bar} aria-label="Platform highlights">
      {tiles.map((tile, i) => (
        <div key={tile.label} className={styles.tileGroup}>
          <div className={styles.tile}>
            <span className={styles.value}>{tile.value}</span>
            <span className={styles.label}>{tile.label}</span>
          </div>
          {i < tiles.length - 1 && (
            <div className={styles.divider} aria-hidden="true" />
          )}
        </div>
      ))}
    </div>
  );
}
