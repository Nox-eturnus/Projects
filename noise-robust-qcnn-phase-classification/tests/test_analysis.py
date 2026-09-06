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
    _, bracketed = crossing_point(x, y, 0.5)
    assert not bracketed


def test_steepest_change_and_smoothing():
    x = np.linspace(0.0, 1.0, 7)
    y = np.array([0.0, 0.0, 0.1, 0.5, 0.9, 1.0, 1.0])
    z = moving_average(y, 3)
    assert len(z) == len(y)
    point = steepest_change_point(x, z)
    assert 0.3 <= point <= 0.7