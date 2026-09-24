from app.services.widget_data import shape_dual_series, shape_series, SHAPERS


def test_butterfly_reuses_shape_dual_series():
    """Butterfly's data shape ({name, value, value2}) is identical to dual_series'
    output -- no dedicated shaper needed, same pattern as bar/line/pie reusing
    shape_series in Phase 0."""
    assert SHAPERS["butterfly"] is shape_dual_series


def test_word_cloud_reuses_shape_series():
    """Word Cloud's data shape ({name, value} per word) is identical to
    shape_series' grouped-series output -- no dedicated shaper needed."""
    assert SHAPERS["word_cloud"] is shape_series
