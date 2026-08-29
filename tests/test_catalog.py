from pool_selector.catalog import Filters, load_catalog, pool_matches


def test_catalog_resolves_r6_xlarge():
    catalog = load_catalog()
    spec = catalog["r6.xlarge"]
    assert spec.category == "memory"
    assert spec.vcpu == 4
    assert spec.memory_gib == 32


def test_unknown_instance_type_is_not_a_candidate():
    catalog = load_catalog()
    assert not pool_matches("pool-g6.xlarge-us-east-1a", catalog, Filters())


def test_filter_category():
    catalog = load_catalog()
    assert pool_matches("pool-r6.xlarge-us-east-1a", catalog, Filters(category="memory"))
    assert not pool_matches("pool-c6.xlarge-us-east-1a", catalog, Filters(category="memory"))


def test_filter_instance_types():
    catalog = load_catalog()
    allowed = ("r6.xlarge", "r6.2xlarge")
    assert pool_matches("pool-r6.xlarge-us-east-1a", catalog, Filters(instance_types=allowed))
    assert not pool_matches("pool-c6.xlarge-us-east-1a", catalog, Filters(instance_types=allowed))


def test_filter_min_vcpu():
    catalog = load_catalog()
    assert pool_matches("pool-r6.2xlarge-us-east-1a", catalog, Filters(min_vcpu=8))
    assert not pool_matches("pool-r6.xlarge-us-east-1a", catalog, Filters(min_vcpu=8))


def test_filter_min_memory():
    catalog = load_catalog()
    assert pool_matches("pool-r6.2xlarge-us-east-1a", catalog, Filters(min_memory=64))
    assert not pool_matches("pool-r6.xlarge-us-east-1a", catalog, Filters(min_memory=64))


def test_filter_az():
    catalog = load_catalog()
    assert pool_matches("pool-r6.xlarge-us-east-1a", catalog, Filters(az=("us-east-1a",)))
    assert not pool_matches("pool-r6.xlarge-us-east-1c", catalog, Filters(az=("us-east-1a",)))


def test_combined_filters_are_intersection():
    catalog = load_catalog()
    filters = Filters(category="memory", az=("us-east-1a",))
    assert pool_matches("pool-r6.xlarge-us-east-1a", catalog, filters)
    assert not pool_matches("pool-r6.xlarge-us-east-1c", catalog, filters)
    assert not pool_matches("pool-c6.xlarge-us-east-1a", catalog, filters)
