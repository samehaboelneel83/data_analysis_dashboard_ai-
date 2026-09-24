import { Database, FolderOpen, Plug } from 'lucide-react'
import { EmptyState } from 'datalytics-frontend'

// Copy is taken from the surfaces that already use this in the product, so the
// card shows the real register: state the absence, then name the next action.

export function TitleOnly() {
  return <EmptyState icon={FolderOpen} title="No reports yet" />
}

export function WithDescription() {
  return (
    <EmptyState
      icon={Database}
      title="No datasets yet"
      description="Import a file or connect a source to start building reports."
    />
  )
}

export function WithAction() {
  return (
    <EmptyState
      icon={Plug}
      title="No connections"
      description="Datalytics reads from Postgres, MySQL, SQL Server, BigQuery and uploaded files."
      action={<button className="btn btn-primary">Add a connection</button>}
    />
  )
}
