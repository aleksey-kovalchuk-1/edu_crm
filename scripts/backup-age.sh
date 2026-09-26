#!/usr/bin/env bash
# Shared age preflight for backup producers. Source this file; no keys are printed.

backup_age_recipient_preflight() {
  command -v age >/dev/null || { echo 'age is required' >&2; return 2; }
  AGE_RECIPIENT_ARGS=()
  if [[ -n "${BACKUP_AGE_RECIPIENTS_FILE:-}" ]]; then
    [[ -f "$BACKUP_AGE_RECIPIENTS_FILE" && -r "$BACKUP_AGE_RECIPIENTS_FILE" && -s "$BACKUP_AGE_RECIPIENTS_FILE" ]] || {
      echo 'BACKUP_AGE_RECIPIENTS_FILE must be a readable, nonempty file' >&2; return 2;
    }
    AGE_RECIPIENT_ARGS=(-R "$BACKUP_AGE_RECIPIENTS_FILE")
  elif [[ -n "${BACKUP_AGE_RECIPIENT:-}" ]]; then
    AGE_RECIPIENT_ARGS=(-r "$BACKUP_AGE_RECIPIENT")
  else
    echo 'BACKUP_AGE_RECIPIENT or BACKUP_AGE_RECIPIENTS_FILE is required' >&2
    return 2
  fi
  age "${AGE_RECIPIENT_ARGS[@]}" -o /dev/null </dev/null || {
    echo 'age recipient preflight failed' >&2; return 2;
  }
}

backup_private_directory() {
  mkdir -p -m 700 "$BACKUP_DIR"
  local mode
  mode="$(stat -c %a "$BACKUP_DIR" 2>/dev/null || stat -f %Lp "$BACKUP_DIR")"
  if (( (8#$mode & 077) != 0 )); then
    echo 'BACKUP_DIR must not be accessible to group or others (chmod 700)' >&2
    return 2
  fi
}
