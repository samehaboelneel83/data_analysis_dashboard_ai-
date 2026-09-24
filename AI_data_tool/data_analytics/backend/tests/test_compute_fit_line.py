from app.services.widget_data import compute_fit_line


def test_linear_fit_recovers_a_known_line():
    xs = [0, 1, 2, 3, 4]
    ys = [1, 3, 5, 7, 9]  # y = 2x + 1
    points = compute_fit_line(xs, ys, "linear")
    assert points is not None
    assert len(points) == 20
    # endpoints should closely match the known line
    assert abs(points[0]["y"] - (2 * points[0]["x"] + 1)) < 0.01
    assert abs(points[-1]["y"] - (2 * points[-1]["x"] + 1)) < 0.01


def test_quadratic_fit_recovers_a_known_parabola():
    xs = [-2, -1, 0, 1, 2]
    ys = [4, 1, 0, 1, 4]  # y = x^2
    points = compute_fit_line(xs, ys, "quadratic")
    mid = points[len(points) // 2]
    assert abs(mid["y"] - mid["x"] ** 2) < 0.5


def test_best_fit_picks_highest_r_squared():
    xs = [0, 1, 2, 3, 4]
    ys = [1, 3, 5, 7, 9]  # perfectly linear
    points = compute_fit_line(xs, ys, "best_fit")
    assert points is not None
    assert abs(points[0]["y"] - (2 * points[0]["x"] + 1)) < 0.5


def test_insufficient_points_returns_none():
    assert compute_fit_line([1], [1], "linear") is None
    assert compute_fit_line([], [], "linear") is None


def test_invalid_kind_returns_none():
    assert compute_fit_line([1, 2, 3], [1, 2, 3], "pspline") is None
