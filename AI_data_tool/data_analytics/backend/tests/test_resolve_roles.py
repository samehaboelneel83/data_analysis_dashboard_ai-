from app.services.widget_data import resolve_roles


def test_legacy_keys_map_to_roles():
    config = {"dimension": "region", "dimension2": "product", "measure": "revenue"}
    assert resolve_roles(config) == {"category": "region", "category2": "product", "measure": "revenue"}


def test_missing_legacy_keys_are_omitted():
    config = {"dimension": "region"}
    assert resolve_roles(config) == {"category": "region"}


def test_explicit_roles_key_takes_precedence():
    config = {"dimension": "region", "roles": {"category": "country", "size": "population"}}
    assert resolve_roles(config) == {"category": "country", "size": "population"}


def test_empty_config_returns_empty_roles():
    assert resolve_roles({}) == {}


def test_explicit_empty_roles_means_no_roles_not_legacy_fallback():
    config = {"dimension": "region", "measure": "revenue", "roles": {}}
    assert resolve_roles(config) == {}


def test_legacy_measure2_and_start_keys_are_recognized():
    config = {"start": "month", "measure": "revenue", "measure2": "cost"}
    assert resolve_roles(config) == {"start": "month", "measure": "revenue", "measure2": "cost"}


def test_all_legacy_role_keys_map_to_themselves_or_a_known_rename():
    """Every role key WidgetConfigPanel.tsx can emit must be present in _LEGACY_ROLE_KEYS,
    or resolve_roles silently drops that role's value.

    The panel emits by TWO routes, and this test originally covered only the first:
      * single roles  -> config[configKeyFor(role)] = value
      * multi roles   -> config[role] = values          (no configKeyFor, role name as-is)

    "measures" is the multi-role case. It was missing, so every Card configured through
    the UI resolved to no measures and rendered zero rows -- configurable, and blank.
    The widget's own tests passed throughout because they exercise the `roles` form,
    not the flat form the panel writes.
    """
    from app.services.widget_data import _LEGACY_ROLE_KEYS
    assert _LEGACY_ROLE_KEYS == {
        "dimension": "category",
        "dimension2": "category2",
        "measure": "measure",
        "measure2": "measure2",
        "start": "start",
        "size": "size",
        "color": "color",
        "group": "group",
        "animation": "animation",
        "end": "end",
        "target": "target",
        "direction": "direction",
        "measures": "measures",
        "lat": "lat",
        "lon": "lon",
        "lat2": "lat2",
        "lon2": "lon2",
    }


def test_legacy_bubble_role_keys_are_recognized():
    """Phase 2 close-out regression: shape_bubble's size/color/group roles are emitted by
    WidgetConfigPanel.tsx as their own flat config keys (configKeyFor's `?? role` fallback,
    since ROLE_TO_CONFIG_KEY only renames category/category2/measure). Without matching
    entries in _LEGACY_ROLE_KEYS, resolve_roles's legacy fallback path would silently drop
    size/color/group/animation for every widget saved via the normal flat-config UI flow
    (the frontend never sends a 'roles' key) — the same class of bug Phase 1's close-out
    caught for measure2/start.

    Note: the category role's legacy config key is "dimension" (per
    WidgetConfigPanel.tsx's ROLE_TO_CONFIG_KEY), not "category" itself — there is no
    "category": "category" self-mapping in _LEGACY_ROLE_KEYS, so a config keyed by the
    literal string "category" would NOT round-trip. This test uses "dimension" for that
    reason, matching what the frontend actually emits.
    """
    config = {
        "dimension": "region", "measure": "x", "measure2": "y",
        "size": "s", "color": "c", "group": "g",
    }
    assert resolve_roles(config) == {
        "category": "region", "measure": "x", "measure2": "y",
        "size": "s", "color": "c", "group": "g",
    }


def test_legacy_phase3_role_keys_are_recognized():
    """Phase 3 close-out regression: Schedule's `end`, Gauge's `target`, and Vector Plot's
    `direction` roles are emitted by WidgetConfigPanel.tsx as their own flat config keys
    (configKeyFor's `?? role` fallback, since ROLE_TO_CONFIG_KEY only renames
    category/category2/measure). Without matching entries in _LEGACY_ROLE_KEYS,
    resolve_roles's legacy fallback path would silently drop end/target/direction for
    every widget saved via the normal flat-config UI flow (the frontend never sends a
    'roles' key in production) — the same class of bug Phase 1's close-out caught for
    measure2/start, and Phase 2's close-out caught for size/color/group/animation.

    This test round-trips all six roles relevant to this phase's chart types together:
    category, start, end (Schedule), measure, target (Gauge), direction (Vector Plot).

    Note: as in test_legacy_bubble_role_keys_are_recognized above, the category role's
    legacy config key is "dimension" (per WidgetConfigPanel.tsx's ROLE_TO_CONFIG_KEY),
    not "category" itself — there is no "category": "category" self-mapping in
    _LEGACY_ROLE_KEYS, so a config keyed by the literal string "category" would NOT
    round-trip. This test uses "dimension" for that reason, matching what the frontend
    actually emits.
    """
    config = {
        "dimension": "task", "start": "s", "end": "e",
        "measure": "x", "target": "t", "direction": "d",
    }
    assert resolve_roles(config) == {
        "category": "task", "start": "s", "end": "e",
        "measure": "x", "target": "t", "direction": "d",
    }
