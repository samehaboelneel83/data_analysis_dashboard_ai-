"""Dashboard templates: a dashboard as a reusable SPECIFICATION.

A template stores what a dashboard is made of -- pages, layouts, widget
settings, metric definitions, filters, style -- with the columns taken out and
replaced by named SLOTS ("a number", "a date", "a category"). Using a template
on a dataset is: map each slot to a column of that dataset, check the mapping,
resolve the specification into real pages. The same specification therefore
draws on any data that has the shape it asks for.

    spec.py       the specification, and what makes one valid
    builtin.py    the platform's own templates (named for what they show,
                  never for a line of business)
    mapping.py    dataset columns -> slots: suggestion, validation, fit
    resolve.py    specification + mapping -> pages, widgets, measures
    capture.py    an existing dashboard -> specification (save as template)
"""
