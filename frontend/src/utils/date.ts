/**
 * date — Shared date and timestamp formatting utilities.
 *
 * REACT CONCEPT: "Utility Functions"
 * ──────────────────────────────────────────────────────────────────
 * Centralizes date conversions so that all future timestamped views
 * (Sessions, Runtime Events, Analytics) display dates in a consistent,
 * standardized format.
 */

/**
 * Formats an ISO-8601 timestamp string into a fixed format: YYYY-MM-DD HH:mm:ss
 * in the operator's local timezone.
 */
export function formatTimestamp(timestamp: string): string {
  try {
    const d = new Date(timestamp)
    
    // Check for invalid dates
    if (isNaN(d.getTime())) {
      return timestamp
    }

    const YYYY = d.getFullYear()
    const MM = String(d.getMonth() + 1).padStart(2, '0')
    const DD = String(d.getDate()).padStart(2, '0')
    const HH = String(d.getHours()).padStart(2, '0')
    const mm = String(d.getMinutes()).padStart(2, '0')
    const ss = String(d.getSeconds()).padStart(2, '0')
    
    return `${YYYY}-${MM}-${DD} ${HH}:${mm}:${ss}`
  } catch {
    return timestamp
  }
}
