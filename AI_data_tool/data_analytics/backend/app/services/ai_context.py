"""What people have WRITTEN about themselves and their data, gathered for a
model that designs for them.

A suggested dashboard was tailored only to what the person typed at that
moment. Four descriptions already sat in the product, unread by the designer:
what the person wrote about themselves on their profile, what the connection
is, what the dataset is, and what the dashboard is for. Here they become one
short block of text, used in two ways:

  * when the box is left empty, the profile's "about me" stands in for it --
    so a person who has described themselves once is designed for every time
    (only where a model is on: without one nothing reads prose);
  * the rest travels after their own words, labelled as background.

Only descriptions of things this reader may already open are passed in by the
callers; nothing here loads or checks access. Each is cut to a few sentences:
it is context, not the question.
"""
from __future__ import annotations

#: The most of any one description that is passed on.
EACH = 500


def _clean(text) -> str:
    return " ".join(str(text or "").split())[:EACH]


def background(*, about=None, connection=None, connection_name=None, dataset=None, dataset_name=None,
               dashboard=None, dashboard_name=None) -> list[str]:
    """One labelled line for each description that exists."""
    out = []
    if _clean(about):
        out.append(f"About the person (from their profile): {_clean(about)}")
    if _clean(connection):
        out.append(f"The connection{f' {_clean(connection_name)!r}' if _clean(connection_name) else ''} is described as: "
                   f"{_clean(connection)}")
    if _clean(dataset):
        out.append(f"The dataset{f' {_clean(dataset_name)!r}' if _clean(dataset_name) else ''} is described as: "
                   f"{_clean(dataset)}")
    if _clean(dashboard):
        out.append(f"The dashboard{f' {_clean(dashboard_name)!r}' if _clean(dashboard_name) else ''} is for: "
                   f"{_clean(dashboard)}")
    return out


def compose(typed: str | None, *, llm_on: bool, **described) -> str:
    """The text a designer is given as "the person": their own words first,
    then the background. With nothing typed, their profile's description
    stands in -- but only where a model will read it (`llm_on`); otherwise an
    empty box stays empty and the statistics engine answers at once."""
    typed = (typed or "").strip()
    if not llm_on:
        return typed
    about = _clean(described.get("about"))
    if not typed:
        if not about:
            return ""
        lines = background(**{**described, "about": None})
        return about + ("\n\nBackground written by people who know this data:\n- " + "\n- ".join(lines)
                        if lines else "")
    lines = background(**described)
    return typed + ("\n\nBackground written by people who know this person and this data:\n- " + "\n- ".join(lines)
                    if lines else "")


async def for_dataset(db, user, ds, typed: str | None, *, report=None) -> str:
    """`compose` for a suggestion made from a dataset (and, when given, for a dashboard)."""
    from ..core.config import settings
    source = None
    if getattr(ds, "data_source_id", None):
        from ..models.models import DataSource
        source = await db.get(DataSource, ds.data_source_id)
        if source is not None and source.org_id != user.org_id:
            source = None
    return compose(typed, llm_on=bool(settings.llm_enabled), about=getattr(user, "about", None),
                   connection=getattr(source, "description", None), connection_name=getattr(source, "name", None),
                   dataset=getattr(ds, "description", None), dataset_name=getattr(ds, "name", None),
                   dashboard=getattr(report, "description", None), dashboard_name=getattr(report, "name", None))
