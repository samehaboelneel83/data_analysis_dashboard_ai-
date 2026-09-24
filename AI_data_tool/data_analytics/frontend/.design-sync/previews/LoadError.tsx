import { LoadError } from 'datalytics-frontend'

// The three cells are the three things `error` can be, because which one you
// pass decides what the user reads: nothing -> the generic reassurance that the
// data is not gone; an axios failure -> the server's own detail; an Error ->
// its message.

export function NoDetail() {
  return <LoadError what="reports" />
}

export function WithRetry() {
  return <LoadError what="the lineage graph" onRetry={() => {}} />
}

export function ServerDetail() {
  return (
    <LoadError
      what="this dataset"
      error={{ response: { data: { detail: 'Connection to source "warehouse-prod" timed out after 30s.' } } }}
      onRetry={() => {}}
    />
  )
}
