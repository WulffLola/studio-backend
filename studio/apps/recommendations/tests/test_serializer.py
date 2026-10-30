from apps.recommendations.serializer import AnalyzeParamsSerializer


def test_params_valid_defaults():
    s = AnalyzeParamsSerializer(data={})
    assert s.is_valid(), s.errors
    assert s.validated_data['window_weeks'] == 8


def test_params_window_weeks_range():
    s = AnalyzeParamsSerializer(data={'window_weeks': 20})
    assert not s.is_valid()
    assert 'window_weeks' in s.errors


def test_params_ratio_range():
    s = AnalyzeParamsSerializer(data={'high_occupancy_ratio': 1.5})
    assert not s.is_valid()
    assert 'high_occupancy_ratio' in s.errors


def test_params_exclusive_bounds():
    for field in ('high_occupancy_threshold', 'high_occupancy_ratio', 'low_occupancy_ratio'):
        assert not AnalyzeParamsSerializer(data={field: 0}).is_valid()
        assert AnalyzeParamsSerializer(data={field: 1}).is_valid()
    assert not AnalyzeParamsSerializer(data={'low_occupancy_threshold': 1}).is_valid()
    assert AnalyzeParamsSerializer(data={'low_occupancy_threshold': 0}).is_valid()
