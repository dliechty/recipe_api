from migrate_access import should_skip_recipe, normalize_ingredient, fix_ingredient_precision

def test_normalize_ingredient():
    # Target case
    assert normalize_ingredient(0, "As Needed") == (0, "To Taste")
    assert normalize_ingredient(0, "as needed") == (0, "To Taste")
    assert normalize_ingredient(0.0, "AS NEEDED") == (0, "To Taste")
    assert normalize_ingredient(0, "As Desired") == (0, "To Taste")
    assert normalize_ingredient(0, "as desired") == (0, "To Taste")
    
    # Non-matching cases
    assert normalize_ingredient(1, "As Needed") == (1, "As Needed")
    assert normalize_ingredient(0, "Cups") == (0, "Cups")
    assert normalize_ingredient(5, "Grams") == (5, "Grams")
    assert normalize_ingredient(None, "As Needed") == (None, "As Needed")
    assert normalize_ingredient(0, None) == (0, None)

def test_should_skip_recipe():
    assert should_skip_recipe("<<Meta Recipe>>") is True
    assert should_skip_recipe("<<  Meta Recipe  >>") is True
    assert should_skip_recipe("Normal Recipe") is False
    assert should_skip_recipe("<< Unclosed") is False
    assert should_skip_recipe("Unopened >>") is False
    assert should_skip_recipe("") is False
    assert should_skip_recipe(None) is False

def test_fix_ingredient_precision():
    # .33 -> .333
    assert fix_ingredient_precision(0.33) == 0.333
    assert fix_ingredient_precision(1.33) == 1.333
    
    # .66 -> .666
    assert fix_ingredient_precision(0.66) == 0.666
    assert fix_ingredient_precision(10.66) == 10.666
    
    # .12 -> .125
    assert fix_ingredient_precision(0.12) == 0.125
    assert fix_ingredient_precision(1.12) == 1.125
    
    # No change
    assert fix_ingredient_precision(0.125) == 0.125
    assert fix_ingredient_precision(1.0) == 1.0
    assert fix_ingredient_precision(0.5) == 0.5
    assert fix_ingredient_precision(5) == 5 # int check (but function expects float or checks isinstance)
    assert fix_ingredient_precision("0.12") == "0.12" # non-float check
