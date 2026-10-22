import pytest
from django.urls import NoReverseMatch, reverse


def test_plan_endpoint_removed():
    """ el CRUD de Plan legacy ya no está registrado."""
    with pytest.raises(NoReverseMatch):
        reverse('plan-list')


@pytest.mark.django_db
def test_plan_model_removed():
    """El modelo Plan ya no existe en el app registry."""
    from django.apps import apps
    with pytest.raises(LookupError):
        apps.get_model('plans', 'Plan')
