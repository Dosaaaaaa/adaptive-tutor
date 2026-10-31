import { useEffect, useId, useRef, useState, type ComponentPropsWithRef, type ReactNode } from "react";
import { Link, type LinkProps } from "react-router-dom";
import { copyText } from "../hooks";
import { Icon, type IconName } from "./Icon";

// ---- buttons ----

type Variant = "primary" | "quiet" | "danger";

interface ButtonProps extends ComponentPropsWithRef<"button"> {
  variant?: Variant;
  small?: boolean;
  busy?: boolean;
  icon?: IconName;
}

export function Button({ variant = "quiet", small, busy, icon, children, className, disabled, type = "button", ...rest }: ButtonProps) {
  return (
    <button
      type={type}
      className={["btn", `btn--${variant}`, small ? "btn--small" : "", className ?? ""].filter(Boolean).join(" ")}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      {...rest}
    >
      {busy ? <Icon name="spinner" className="icon--spin" /> : icon ? <Icon name={icon} /> : null}
      {children}
    </button>
  );
}

interface ButtonLinkProps extends LinkProps {
  variant?: Variant;
  small?: boolean;
  icon?: IconName;
}

export function ButtonLink({ variant = "quiet", small, icon, children, className, ...rest }: ButtonLinkProps) {
  return (
    <Link className={["btn", `btn--${variant}`, small ? "btn--small" : "", className ?? ""].filter(Boolean).join(" ")} {...rest}>
      {icon ? <Icon name={icon} /> : null}
      {children}
    </Link>
  );
}

/** An address that downloads a file. */
export function DownloadLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a className="btn btn--quiet" href={href} download>
      <Icon name="download" />
      {children}
    </a>
  );
}

// ---- copy ----

export function CopyButton({ text, label = "Copy link", small }: { text: string; label?: string; small?: boolean }) {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(timer.current), []);

  async function copy() {
    setState((await copyText(text)) ? "copied" : "failed");
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setState("idle"), 2200);
  }

  return (
    <>
      <Button small={small} icon={state === "copied" ? "check" : "copy"} onClick={() => void copy()}>
        {state === "copied" ? "Copied" : state === "failed" ? "Copy failed" : label}
      </Button>
      <span className="visually-hidden" role="status">
        {state === "copied" ? "Copied to the clipboard." : state === "failed" ? "Could not copy. Select the link and copy it by hand." : ""}
      </span>
    </>
  );
}

// ---- a risky action that asks once, in place ----

export function ConfirmButton({
  label, question, confirmLabel, onConfirm, icon = "trash", busy,
}: { label: string; question: string; confirmLabel: string; onConfirm: () => void; icon?: IconName; busy?: boolean }) {
  const [asking, setAsking] = useState(false);
  const keep = useRef<HTMLButtonElement>(null);
  const first = useRef<HTMLButtonElement>(null);
  const wasAsking = useRef(false);

  useEffect(() => {
    if (asking) keep.current?.focus();
    else if (wasAsking.current) first.current?.focus();
    wasAsking.current = asking;
  }, [asking]);

  if (!asking) {
    return <Button ref={first} icon={icon} onClick={() => setAsking(true)}>{label}</Button>;
  }
  return (
    <span className="confirm" role="group" aria-label={question}>
      <span className="confirm__ask">{question}</span>
      <Button variant="danger" small busy={busy} onClick={onConfirm}>{confirmLabel}</Button>
      <Button ref={keep} small onClick={() => setAsking(false)}>Keep it</Button>
    </span>
  );
}

// ---- form fields ----

interface FieldProps {
  label: string;
  hint?: ReactNode;
  error?: string | null;
  children: (control: { id: string; "aria-describedby"?: string; "aria-invalid"?: true }) => ReactNode;
}

/** A label, a hint and an error tied to one control so a screen reader reads them together. */
export function Field({ label, hint, error, children }: FieldProps) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const described = [hintId, errorId].filter(Boolean).join(" ") || undefined;
  return (
    <div className="field" data-invalid={error ? "true" : undefined}>
      <label className="field__label" htmlFor={id}>{label}</label>
      {hint ? <p className="field__hint" id={hintId}>{hint}</p> : null}
      {children({ id, "aria-describedby": described, "aria-invalid": error ? true : undefined })}
      {error ? <p className="field__error" id={errorId}><Icon name="alert" size={14} />{error}</p> : null}
    </div>
  );
}

// ---- a small segmented switch built from radio buttons ----

export function Segmented<T extends string>({
  name, legend, value, options, onChange,
}: { name: string; legend: string; value: T; options: { value: T; label: string }[]; onChange: (value: T) => void }) {
  return (
    <fieldset className="segmented">
      <legend className="visually-hidden">{legend}</legend>
      {options.map((o) => (
        <label key={o.value} className="segmented__option">
          <input type="radio" name={name} value={o.value} checked={value === o.value} onChange={() => onChange(o.value)} />
          <span>{o.label}</span>
        </label>
      ))}
    </fieldset>
  );
}
