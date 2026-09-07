import numpy as np

from qcnn_lab.analysis.transition import crossing_point, moving_average, steepest_change_point


def test_crossing_interpolates():
    x = np.array([0.0, 1.0, 2.0])
    y = np.array([0.1, 0.4, 0.8])
    cross, bracketed = crossing_point(x, y, 0.5)
    assert bracketed
    assert np.isclose(cross, 1.25)


def test_non_crossing_is_explicit():
    x = np.array([0.0, 1.0, 2.0])
    y = np.array([0.1, 0.2, 0.3])
    cross, bracketed = crossing_point(x, y, 0.5)
    assert not bracketed
    assert cross is None


def test_flat_curve_returns_none():
    x = np.array([0.0, 1.0, 2.0, 3.0])
    y = np.array([0.5, 0.5, 0.5, 0.5])
    cross, bracketed = crossing_point(x, y, 0.5)
    assert not bracketed
    assert cross is None


def test_plateau_crossing():
    x = np.array([0.0, 1.0, 2.0, 3.0])
    y = np.array([0.2, 0.5, 0.5, 0.8])
    cross, bracketed = crossing_point(x, y, 0.5)
    assert bracketed
    assert np.isclose(cross, 1.5)


def test_multiple_crossings_selects_largest_contrast():
    x = np.array([0.0, 1.0, 2.0, 3.0])
    # Crossing 1 between x=0 and x=1: contrast 0.49 -> 0.51 (0.02)
    # Crossing 2 between x=2 and x=3: contrast 0.10 -> 0.90 (0.80)
    y = np.array([0.49, 0.51, 0.10, 0.90])
    cross, bracketed = crossing_point(x, y, 0.5)
    assert bracketed
    assert 2.0 < cross < 3.0


def test_steepest_change_and_smoothing():
    x = np.linspace(0.0, 1.0, 7)
    y = np.array([0.0, 0.0, 0.1, 0.5, 0.9, 1.0, 1.0])
    z = moving_average(y, 3)
    assert len(z) == len(y)
    point = steepest_change_point(x, z)
    assert 0.3 <= point <= 0.7