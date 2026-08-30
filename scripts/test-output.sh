#!/usr/bin/env bash
# Sourceable bounded-output helper for long-running test commands.

run_with_log() {
  if [ "$#" -lt 4 ]; then
    echo "run_with_log requires: label first_lines last_lines command..." >&2
    return 64
  fi

  local label="$1"
  local first_lines="$2"
  local last_lines="$3"
  shift 3

  local temp_root="${TMPDIR:-/tmp}"
  local log_file
  if ! log_file="$(mktemp "${temp_root%/}/reva-test-output.XXXXXX")"; then
    echo "cannot create temporary test log under ${temp_root}" >&2
    return 125
  fi

  "$@" >"$log_file" 2>&1
  local status=$?

  local line_count
  line_count="$(wc -l <"$log_file")"
  if [ -s "$log_file" ] && [ "$line_count" -eq 0 ]; then
    line_count=1
  fi

  if [ "$status" -eq 0 ]; then
    if [ -s "$log_file" ]; then
      local success_start=1
      if [ "$line_count" -gt "$last_lines" ]; then
        success_start=$((line_count - last_lines + 1))
      fi
      sed -n "${success_start},${line_count}p" "$log_file"
    fi
  else
    echo "${label} failed with exit ${status}" >&2
    if [ ! -s "$log_file" ]; then
      echo "(command produced no output)" >&2
    elif [ "$line_count" -le $((first_lines + last_lines)) ]; then
      sed -n '1,$p' "$log_file" >&2
    else
      echo "--- first ${first_lines} lines ---" >&2
      sed -n "1,${first_lines}p" "$log_file" >&2
      echo "--- $((line_count - first_lines - last_lines)) lines omitted ---" >&2
      echo "--- last ${last_lines} lines ---" >&2
      local last_start=$((line_count - last_lines + 1))
      sed -n "${last_start},${line_count}p" "$log_file" >&2
    fi
  fi

  if ! rm -f "$log_file"; then
    echo "failed to remove temporary test log: ${log_file}" >&2
    if [ "$status" -eq 0 ]; then
      status=125
    fi
  fi
  return "$status"
}
