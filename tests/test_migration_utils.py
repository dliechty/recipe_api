from migrate_access import should_skip_recipe

def test_should_skip_recipe():
    assert should_skip_recipe("<<Meta Recipe>>") is True
    assert should_skip_recipe("<<  Meta Recipe  >>") is True
    assert should_skip_recipe("Normal Recipe") is False
    assert should_skip_recipe("<< Unclosed") is False
    assert should_skip_recipe("Unopened >>") is False
    assert should_skip_recipe("") is False
    assert should_skip_recipe(None) is False
