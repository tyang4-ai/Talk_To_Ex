import type { InputHTMLAttributes, TextareaHTMLAttributes } from "react";

interface FieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
}

/** Labeled text input used across Auth and Intake. */
export function Field({ label, id, ...rest }: FieldProps) {
  const fieldId = id || rest.name || label.toLowerCase().replace(/\s+/g, "-");
  return (
    <div>
      <label htmlFor={fieldId} className="field-label">
        {label}
      </label>
      <input id={fieldId} className="field" {...rest} />
    </div>
  );
}

interface TextAreaFieldProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label: string;
}

/** Labeled multiline input (Intake "how you met", plaintext paste fallback). */
export function TextAreaField({ label, id, rows = 3, ...rest }: TextAreaFieldProps) {
  const fieldId = id || rest.name || label.toLowerCase().replace(/\s+/g, "-");
  return (
    <div>
      <label htmlFor={fieldId} className="field-label">
        {label}
      </label>
      <textarea id={fieldId} rows={rows} className="field-area" {...rest} />
    </div>
  );
}
