/** A bar for a measured value. The number is always written next to it, so the bar never has to carry it alone. */
export function Meter({ value, max = 100, label, tone = "measure" }: { value: number; max?: number; label: string; tone?: "measure" | "person" }) {
  const fraction = max > 0 ? Math.min(1, Math.max(0, value / max)) : 0;
  return (
    <div className="meter" role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={max} aria-valuenow={Math.round(value)} data-tone={tone}>
      <span className="meter__fill" style={{ transform: `scaleX(${fraction})` }} />
    </div>
  );
}
