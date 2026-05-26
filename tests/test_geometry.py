from geometry import Line2D, perpendicular_distance_to_line, orthogonal_projection_on_line


def test_perpendicular_distance_to_horizontal_line():
    line = Line2D((0.0, 0.0), (10.0, 0.0))
    point = (5.0, 7.0)
    distance = perpendicular_distance_to_line(point, line)
    assert abs(distance - 7.0) < 1e-9


def test_orthogonal_projection_on_horizontal_line():
    line = Line2D((0.0, 0.0), (10.0, 0.0))
    point = (5.0, 7.0)
    projection = orthogonal_projection_on_line(point, line)
    assert abs(projection[0] - 5.0) < 1e-9
    assert abs(projection[1] - 0.0) < 1e-9