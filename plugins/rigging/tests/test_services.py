import re

from rigging.services import SERVICE_REGISTRY, SERVICE_IDS, ServiceSpec


def test_service_ids_derived_from_registry():
    assert SERVICE_IDS == tuple(SERVICE_REGISTRY)


def test_initial_services_are_postgres_mysql_redis():
    assert set(SERVICE_IDS) == {"postgres", "mysql", "redis"}


def test_image_ref_appends_the_version_tag():
    assert SERVICE_REGISTRY["postgres"].image_ref("16") == "postgres:16"


def test_url_is_composed_from_registry_constants_not_the_version():
    pg = SERVICE_REGISTRY["postgres"]
    # version selects the image tag only; it is not in the URL.
    assert pg.url == "postgresql://postgres:postgres@localhost:5432/postgres"
    assert SERVICE_REGISTRY["redis"].url == "redis://localhost:6379"
    assert SERVICE_REGISTRY["mysql"].url == "mysql://root:mysql@localhost:3306/mysql"


def test_every_service_carries_a_health_check():
    # The health check is the whole reason this is a registry; none may be empty.
    for sid, spec in SERVICE_REGISTRY.items():
        assert "--health-cmd" in spec.health_options, sid


def test_health_options_carry_no_actions_expression():
    for spec in SERVICE_REGISTRY.values():
        assert "${{" not in spec.health_options
