import { useMode, type Mode } from "../hooks";
import { Icon, type IconName } from "./Icon";

const CHOICES: { mode: Mode; label: string; icon: IconName }[] = [
  { mode: "system", label: "Match my device", icon: "monitor" },
  { mode: "light", label: "Light", icon: "sun" },
  { mode: "dark", label: "Dark", icon: "moon" },
];

export function ThemeToggle() {
  const [mode, setMode] = useMode();
  return (
    <div className="modes" role="group" aria-label="Colour mode">
      {CHOICES.map((c) => (
        <button
          key={c.mode}
          type="button"
          className="modes__btn"
          aria-pressed={mode === c.mode}
          aria-label={c.label}
          title={c.label}
          onClick={() => setMode(c.mode)}
        >
          <Icon name={c.icon} />
        </button>
      ))}
    </div>
  );
}
