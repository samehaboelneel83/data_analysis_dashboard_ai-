/**
 * Turns a driver-level error string into something a person can act on.
 *
 * The backend passes some database exceptions straight through as `detail`,
 * so a failed connection used to toast
 *   "(psycopg2.OperationalError) could not translate host name "qa-db.invalid"
 *    to address: Name or service not known (Background on this error at:
 *    https://sqlalche.me/e/20/e3q8)"
 * -- accurate, and useless to anyone who is not reading the server's source.
 * Messages that are already written for people pass through untouched; only
 * ones that carry a driver's fingerprints are rewritten. The original is kept
 * on the error (`detail_raw`) for whoever needs to debug it.
 */

const TECHNICAL = /psycopg2?|sqlalchemy|sqlalche\.me|OperationalError|ProgrammingError|InterfaceError|Traceback \(most recent|pymysql|pyodbc|cx_Oracle|\bORA-\d{4,5}\b|\(Background on this error/i

export function isTechnical(message: string): boolean {
  return TECHNICAL.test(message)
}

export function friendlyMessage(message: string): string {
  if (!isTechnical(message)) return message
  const m = message
  if (/could not translate host name|Name or service not known|getaddrinfo|nodename nor servname|Unknown host/i.test(m)) {
    return 'The database server could not be found. Check the host name.'
  }
  if (/on socket .*failed/i.test(m)) {
    return 'No database server was named. Fill in the host (and port).'
  }
  if (/no password supplied|password is required/i.test(m)) {
    return 'The server needs a password for this user.'
  }
  if (/Connection refused|could not connect|timed? ?out|Can't connect|Network is unreachable/i.test(m)) {
    return 'The database server did not answer. Check the host, the port and that the server is running.'
  }
  if (/password authentication failed|Access denied|Login failed|authentication/i.test(m)) {
    return 'The database rejected the username or password.'
  }
  if (/database .* does not exist|Unknown database/i.test(m)) {
    return 'That database does not exist on the server.'
  }
  if (/relation .* does not exist|no such table|Invalid object name|doesn't exist/i.test(m)) {
    return 'A table this query reads no longer exists in the source.'
  }
  if (/permission denied|insufficient privilege/i.test(m)) {
    return 'The database user does not have permission to read this.'
  }
  if (/syntax error/i.test(m)) {
    return 'The source rejected the query as invalid SQL.'
  }
  return 'The database returned an error. Ask an admin to check the connection.'
}

/** Rewrites `error.response.data.detail` in place when it is a driver message. */
export function sanitizeErrorDetail(error: any): void {
  const data = error?.response?.data
  if (!data || data.detail === undefined) return
  // FastAPI's validation errors (422) send `detail` as an ARRAY of objects.
  // Rendered as a React child that threw and took the whole app to a white
  // page; here it becomes one readable sentence and the raw form is kept.
  if (typeof data.detail !== 'string') {
    data.detail_raw = data.detail
    data.detail = detailToText(data.detail)
    return
  }
  if (isTechnical(data.detail)) {
    data.detail_raw = data.detail
    data.detail = friendlyMessage(data.detail)
  }
}

/** Any `detail` shape the server might send, as one sentence. */
export function detailToText(detail: unknown): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const parts = detail.map(d => {
      if (d && typeof d === 'object' && 'msg' in (d as object)) {
        const loc = Array.isArray((d as any).loc) ? (d as any).loc.filter((x: unknown) => x !== 'body' && x !== 'path' && x !== 'query').join('.') : ''
        return loc ? `${loc}: ${(d as any).msg}` : String((d as any).msg)
      }
      return typeof d === 'string' ? d : JSON.stringify(d)
    })
    return parts.length ? `Invalid request — ${parts.join('; ')}` : 'Invalid request'
  }
  if (detail && typeof detail === 'object') {
    const o = detail as Record<string, unknown>
    if (typeof o.message === 'string') return o.message
    if (typeof o.msg === 'string') return o.msg
    return JSON.stringify(detail)
  }
  return String(detail)
}
