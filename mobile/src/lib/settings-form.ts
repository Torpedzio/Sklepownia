import type { SettingsSection } from '@/lib/types';

/** Unsaved edits of one settings section: field → value as typed. */
export type Draft = Record<string, string | boolean>;
export type Drafts = Partial<Record<SettingsSection, Draft>>;
/** Validation messages per section and field, as the settings screen shows them. */
export type FieldErrors = Partial<Record<SettingsSection, Record<string, string>>>;

// Money and rates are typed by people, who may use a comma.
const DECIMAL_FIELDS = new Set(['courier_cost', 'free_shipping_min_amount', 'standard_rate']);

/** The edits that differ from the saved values; text fields compare as text, so "5" equals 5. */
export function changedFields(saved: Record<string, unknown>, draft: Draft | undefined) {
  return Object.fromEntries(Object.entries(draft ?? {}).filter(([key, value]) => String(value) !== String(saved[key])));
}

/** A typed value in the form the API accepts. */
export function toApi(key: string, value: string | boolean) {
  if (typeof value === 'boolean') return value;
  if (DECIMAL_FIELDS.has(key)) return value.replace(',', '.').replace(/\s/g, '');
  if (key === 'low_stock_threshold' && /^\d+$/.test(value.trim())) return Number(value.trim());
  return value;
}

/** The first message per field from a 400 response, `{section: {field: [messages]}}`. */
export function sectionErrors(data: Record<string, unknown> | null): FieldErrors {
  const result: FieldErrors = {};
  for (const [section, fields] of Object.entries(data ?? {})) {
    if (!fields || typeof fields !== 'object' || Array.isArray(fields)) continue;
    result[section as SettingsSection] = Object.fromEntries(
      Object.entries(fields as Record<string, unknown>).map(([field, messages]) => [
        field,
        Array.isArray(messages) ? String(messages[0]) : String(messages),
      ]),
    );
  }
  return result;
}

/** "dziś, 10:42" or "4 listopada, 10:42". */
export function formatTime(iso: string, now = new Date()) {
  const date = new Date(iso);
  const today = now.toDateString() === date.toDateString();
  const time = date.toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit' });
  return today ? `dziś, ${time}` : `${date.toLocaleDateString('pl-PL', { day: 'numeric', month: 'long' })}, ${time}`;
}
