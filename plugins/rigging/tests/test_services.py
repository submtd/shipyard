from rigging.services import SERVICE_REGISTRY, SERVICE_IDS, ServiceSpec


def test_service_ids_derived_from_registry():
    assert SERVICE_IDS == tuple(SERVICE_REGISTRY)


def test_initial_services_are_postgres_mysql_redis():
    assert set(SERVICE_IDS) == {"postgres", "mysql", "redis"}


def test_image_ref_appends_the_version_tag():
    assert SERVICE_REGISTRY["postgres"].image_ref("16") == "postgres:16"


def test_url_is_composed_from_registry_constants_and_the_default_database():
    pg = SERVICE_REGISTRY["postgres"]
    # version selects the image tag only; it is not in the URL. The database
    # defaults to the service's default_database, reproducing the historic URL.
    assert pg.url(pg.default_database) == \
        "postgresql://postgres:postgres@localhost:5432/postgres"
    mysql = SERVICE_REGISTRY["mysql"]
    assert mysql.url(mysql.default_database) == \
        "mysql://root:mysql@localhost:3306/mysql"


def test_url_interpolates_a_chosen_database():
    assert SERVICE_REGISTRY["postgres"].url("onelife_test") == \
        "postgresql://postgres:postgres@localhost:5432/onelife_test"


def test_redis_url_ignores_the_database_argument():
    # redis has no database concept; its template has no {database} placeholder,
    # so the argument is dropped rather than raising.
    assert SERVICE_REGISTRY["redis"].url(None) == "redis://localhost:6379"
    assert SERVICE_REGISTRY["redis"].url("anything") == "redis://localhost:6379"


def test_database_env_and_default_database_are_correct_per_service():
    assert SERVICE_REGISTRY["postgres"].database_env == "POSTGRES_DB"
    assert SERVICE_REGISTRY["postgres"].default_database == "postgres"
    assert SERVICE_REGISTRY["mysql"].database_env == "MYSQL_DATABASE"
    assert SERVICE_REGISTRY["mysql"].default_database == "mysql"


def test_redis_has_no_database_concept():
    assert SERVICE_REGISTRY["redis"].database_env is None
    assert SERVICE_REGISTRY["redis"].default_database is None


def test_every_service_carries_a_health_check():
    # The health check is the whole reason this is a registry; none may be empty.
    for sid, spec in SERVICE_REGISTRY.items():
        assert "--health-cmd" in spec.health_options, sid


def test_health_options_carry_no_actions_expression():
    for spec in SERVICE_REGISTRY.values():
        assert "${{" not in spec.health_options
