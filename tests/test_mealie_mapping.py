from migration_scripts.mealie_mapping import slugify


def test_slugify_lowercases_and_hyphenates():
    assert slugify("Mom's Apple Pie!") == "mom-s-apple-pie"


def test_slugify_collapses_and_strips_separators():
    assert slugify("  Beef   &  Broccoli  ") == "beef-broccoli"
