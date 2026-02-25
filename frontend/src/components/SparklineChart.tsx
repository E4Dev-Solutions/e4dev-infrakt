interface DataPoint {
  time: string;
  value: number;
}

interface SparklineChartProps {
  data: DataPoint[];
  color: string;
  fillColor: string;
  label: string;
  height?: number;
}

/**
 * Lightweight SVG sparkline for time-series percentage data (0–100 range).
 * Renders a filled area path with a stroke polyline on top. No external
 * charting library required.
 */
export default function SparklineChart({
  data,
  color,
  fillColor,
  label,
  height = 60,
}: SparklineChartProps) {
  const width = 200;
  const latestValue = data.length > 0 ? data[data.length - 1].value : null;

  if (data.length < 2) {
    return (
      <div className="flex flex-col gap-1">
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium text-slate-400">{label}</span>
          <span className="text-xs text-slate-600">No data</span>
        </div>
        <div
          className="w-full rounded bg-slate-700/40"
          style={{ height }}
          aria-hidden="true"
        />
      </div>
    );
  }

  // Map data points to SVG coordinates.
  // Y-axis: fixed 0–100 percentage scale. Invert Y so 100% = top of SVG.
  const points = data.map((d, i) => {
    const x = (i / (data.length - 1)) * width;
    const y = height - (Math.min(100, Math.max(0, d.value)) / 100) * height;
    return { x, y };
  });

  // Build the polyline points string
  const polylinePoints = points.map((p) => `${p.x},${p.y}`).join(" ");

  // Build the filled area path: trace the line, then close back to the baseline
  const firstPoint = points[0];
  const lastPoint = points[points.length - 1];
  const linePath = points.map((p, i) => `${i === 0 ? "M" : "L"}${p.x},${p.y}`).join(" ");
  const fillPath = `${linePath} L${lastPoint.x},${height} L${firstPoint.x},${height} Z`;

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-slate-400">{label}</span>
        {latestValue !== null && (
          <span className="text-xs font-semibold" style={{ color }}>
            {latestValue.toFixed(1)}%
          </span>
        )}
      </div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        className="w-full rounded"
        style={{ height }}
        aria-label={`${label} sparkline chart`}
        role="img"
      >
        {/* Filled area under the curve */}
        <path d={fillPath} fill={fillColor} />
        {/* Stroke line on top */}
        <polyline
          points={polylinePoints}
          fill="none"
          stroke={color}
          strokeWidth="1.5"
          strokeLinejoin="round"
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
        />
      </svg>
    </div>
  );
}
