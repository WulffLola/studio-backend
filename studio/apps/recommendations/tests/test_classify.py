from apps.recommendations.services import classify, Params

P = Params(window_weeks=8, min_classes=8, high_occupancy_threshold=0.8,
           high_occupancy_ratio=0.6, low_occupancy_threshold=0.5, low_occupancy_ratio=0.6)

def test_insufficient_under_min():
    assert classify([0.9] * 7, P) == 'insufficient'      # 7 < 8

def test_min_classes_is_enough():
    assert classify([0.9] * 8, P) == 'high'              # exactamente 8 -> alcanza

def test_high_demand():
    assert classify([0.9, 0.9, 0.9, 0.9, 0.9, 0.9, 0.2, 0.2], P) == 'high'  # 6/8=0.75≥0.6

def test_low_demand():
    assert classify([0.4] * 6 + [0.9, 0.9], P) == 'low'   # 6/8=0.75≥0.6

def test_medium():
    assert classify([0.9, 0.9, 0.9, 0.4, 0.4, 0.4, 0.7, 0.7], P) == 'medium'
