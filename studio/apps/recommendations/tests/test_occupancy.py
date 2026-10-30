from apps.recommendations.services import occupancy_of, ratio_at_least, ratio_at_most


def test_occupancy_of():
    assert occupancy_of(3, 1) == 0.75          # cupos 4
    assert occupancy_of(0, 0) == 0.0            # sin cupos -> 0, sin ZeroDivision
    assert occupancy_of(2, None) == 1.0         # availability None -> cupos = confirmed


def test_ratios():
    vals = [1.0, 0.9, 0.5, 0.4]
    assert ratio_at_least(vals, 0.8) == 0.5     # 2 de 4
    assert ratio_at_most(vals, 0.5) == 0.5      # 2 de 4
    assert ratio_at_least([], 0.8) == 0.0
