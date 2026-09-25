import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'

/**
 * The breadcrumb's last step: the NAME of the thing a detail page shows.
 *
 * The top bar knows the route ("Datasets") but not the record, so on
 * /datasets/170 it said "Data > Datasets" -- the same trail as the list page,
 * with nothing telling you which dataset you were in. A detail page announces
 * its title here once it has loaded; the bar appends it as the current page.
 *
 * The event carries the path it was sent for, so a title can never outlive
 * its page: the bar only shows a leaf whose path is the one on screen.
 */
export const CRUMB_EVENT = 'datalytics:crumb'

export interface CrumbDetail { path: string; title: string | null }

export function useCrumbTitle(title: string | null | undefined) {
  const { pathname } = useLocation()
  useEffect(() => {
    if (!title) return
    window.dispatchEvent(new CustomEvent<CrumbDetail>(CRUMB_EVENT, { detail: { path: pathname, title } }))
    return () => {
      window.dispatchEvent(new CustomEvent<CrumbDetail>(CRUMB_EVENT, { detail: { path: pathname, title: null } }))
    }
  }, [title, pathname])
}
