import { ApiError } from "@crm/ui";
import type { FieldValues, Path, UseFormSetError } from "react-hook-form";

/** Map API validation details onto react-hook-form fields; returns a general message for the rest. */
export function applyApiErrors<T extends FieldValues>(e: unknown, setError: UseFormSetError<T>, known: string[]): string | null {
  if (!(e instanceof ApiError)) return "Something went wrong. Please try again.";
  let mapped = false;
  for (const [k, msg] of Object.entries(e.details ?? {})) {
    if (known.includes(k)) { setError(k as Path<T>, { message: msg }); mapped = true; }
  }
  return mapped && e.code === "validation_error" ? null : e.message;
}
