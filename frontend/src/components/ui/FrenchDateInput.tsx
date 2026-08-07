import {
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type InputHTMLAttributes,
} from "react";
import { formatDate, parseDateInput } from "../../lib/format";

type FrenchDateInputProps = Omit<
  InputHTMLAttributes<HTMLInputElement>,
  "defaultValue" | "name" | "onChange" | "type" | "value"
> & {
  defaultValue?: string;
  name?: string;
  onValueChange?: (isoValue: string) => void;
  value?: string;
};

const INVALID_DATE_MESSAGE = "Saisissez une date valide au format jj/mm/aaaa.";

function initialValues(value: string) {
  const iso = parseDateInput(value) ?? "";
  return { display: iso ? formatDate(iso) : "", iso };
}

export function FrenchDateInput({
  defaultValue = "",
  disabled,
  name,
  onBlur,
  onValueChange,
  value,
  ...props
}: FrenchDateInputProps) {
  const controlled = value !== undefined;
  const initial = useRef(initialValues(value ?? defaultValue));
  const inputRef = useRef<HTMLInputElement>(null);
  const [displayValue, setDisplayValue] = useState(initial.current.display);
  const [isoValue, setIsoValue] = useState(initial.current.iso);

  useEffect(() => {
    if (!controlled) return;
    const next = initialValues(value ?? "");
    setDisplayValue(next.display);
    setIsoValue(next.iso);
  }, [controlled, value]);

  useEffect(() => {
    const form = inputRef.current?.form;
    if (!form || controlled) return;
    const reset = () => {
      setIsoValue(initial.current.iso);
      inputRef.current?.setCustomValidity("");
    };
    form.addEventListener("reset", reset);
    return () => form.removeEventListener("reset", reset);
  }, [controlled]);

  function change(event: ChangeEvent<HTMLInputElement>) {
    const rawValue = event.currentTarget.value;
    const parsed = parseDateInput(rawValue);
    const empty = rawValue.trim() === "";
    const nextDisplay =
      parsed && rawValue.includes("-") ? formatDate(parsed) : rawValue;
    if (controlled) setDisplayValue(nextDisplay);
    else if (nextDisplay !== rawValue) event.currentTarget.value = nextDisplay;
    setIsoValue(parsed ?? "");
    event.currentTarget.setCustomValidity(
      empty || parsed ? "" : INVALID_DATE_MESSAGE,
    );
    if (parsed || (empty && !props.required)) onValueChange?.(parsed ?? "");
  }

  return (
    <>
      <input
        {...props}
        ref={inputRef}
        type="text"
        lang="fr"
        inputMode="numeric"
        placeholder="jj/mm/aaaa"
        maxLength={10}
        pattern="[0-3][0-9]/[01][0-9]/[0-9]{4}"
        title="Format attendu : jj/mm/aaaa"
        disabled={disabled}
        {...(controlled
          ? { value: displayValue }
          : { defaultValue: initial.current.display })}
        onChange={change}
        onBlur={(event) => {
          const parsed = parseDateInput(event.currentTarget.value);
          if (parsed) {
            const formatted = formatDate(parsed);
            if (controlled) setDisplayValue(formatted);
            else event.currentTarget.value = formatted;
          }
          onBlur?.(event);
        }}
      />
      {name && (
        <input type="hidden" name={name} value={isoValue} disabled={disabled} />
      )}
    </>
  );
}
