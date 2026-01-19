# meal_planning.py
# Service for intelligent meal plan generation with freshness and variety scoring.

import random
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from app import models, schemas, crud, filters


def calculate_freshness_score(
    recipe_id: UUID,
    last_cooked_dates: dict[UUID, datetime],
    freshness_window_days: int = 30
) -> float:
    """
    Calculate freshness score (0.0 - 1.0).

    - 1.0 = never cooked or cooked > freshness_window_days ago
    - 0.0 = cooked today
    - Linear decay between
    """
    last_cooked = last_cooked_dates.get(recipe_id)
    if last_cooked is None:
        return 1.0  # Never cooked = maximally fresh

    now = datetime.now()
    # Handle timezone-aware datetimes
    if last_cooked.tzinfo is not None:
        from datetime import timezone
        now = datetime.now(timezone.utc)

    days_since_cooked = (now - last_cooked).days

    if days_since_cooked >= freshness_window_days:
        return 1.0
    if days_since_cooked <= 0:
        return 0.0

    return days_since_cooked / freshness_window_days


def calculate_variety_score(
    candidate: models.Recipe,
    selected_recipes: list[models.Recipe]
) -> float:
    """
    Calculate variety score (0.0 - 1.0) based on how different the candidate is
    from already-selected recipes.

    Penalties:
    - Same protein: 0.4
    - Same cuisine: 0.25
    - Same category: 0.15

    1.0 = completely different, 0.0 = very similar
    """
    if not selected_recipes:
        return 1.0  # No comparison needed

    total_penalty = 0.0

    for selected in selected_recipes:
        penalty = 0.0

        # Protein match (most significant)
        if candidate.protein and selected.protein:
            if candidate.protein.lower() == selected.protein.lower():
                penalty += 0.4

        # Cuisine match
        if candidate.cuisine and selected.cuisine:
            if candidate.cuisine.lower() == selected.cuisine.lower():
                penalty += 0.25

        # Category match
        if candidate.category and selected.category:
            if candidate.category.lower() == selected.category.lower():
                penalty += 0.15

        total_penalty = max(total_penalty, penalty)  # Take worst match

    return max(0.0, 1.0 - total_penalty)


def calculate_combined_score(
    recipe: models.Recipe,
    last_cooked_dates: dict[UUID, datetime],
    selected_recipes: list[models.Recipe],
    selected_recipe_ids: set[UUID],
    weights: schemas.MealPlanScoringWeights,
    freshness_window_days: int = 30
) -> tuple[float, float, float, float]:
    """
    Calculate combined score for a recipe.

    Returns: (combined_score, freshness_score, variety_score, repetition_multiplier)
    """
    freshness = calculate_freshness_score(
        recipe.id, last_cooked_dates, freshness_window_days
    )
    variety = calculate_variety_score(recipe, selected_recipes)
    random_factor = random.random()

    base_score = (
        weights.freshness_weight * freshness +
        weights.variety_weight * variety +
        weights.random_weight * random_factor
    )

    # Repetition penalty: 0.3 if already in plan, 1.0 otherwise
    repetition_multiplier = 0.3 if recipe.id in selected_recipe_ids else 1.0
    combined_score = base_score * repetition_multiplier

    return combined_score, freshness, variety, repetition_multiplier


def get_eligible_recipes(
    db: Session,
    user_id: UUID,
    constraints: schemas.MealPlanConstraints
) -> list[models.Recipe]:
    """
    Get all recipes that match the given constraints.
    """
    query = db.query(models.Recipe)

    filters_list = []

    # Dietary restrictions - recipes must be suitable for ALL specified diets
    if constraints.dietary_restrictions:
        for diet in constraints.dietary_restrictions:
            filters_list.append(filters.Filter(
                field="suitable_for_diet",
                operator="all",
                value=diet.value
            ))

    # Excluded proteins
    if constraints.excluded_proteins:
        for protein in constraints.excluded_proteins:
            filters_list.append(filters.Filter(
                field="protein",
                operator="neq",
                value=protein
            ))

    # Max difficulty
    if constraints.max_difficulty:
        difficulty_order = {"Easy": 1, "Medium": 2, "Hard": 3}
        max_level = difficulty_order.get(constraints.max_difficulty.value, 3)
        allowed_difficulties = [
            d for d, level in difficulty_order.items() if level <= max_level
        ]
        filters_list.append(filters.Filter(
            field="difficulty",
            operator="in",
            value=",".join(allowed_difficulties)
        ))

    # Max total time
    if constraints.max_total_time_minutes:
        filters_list.append(filters.Filter(
            field="total_time_minutes",
            operator="lte",
            value=str(constraints.max_total_time_minutes)
        ))

    if filters_list:
        query = filters.apply_filters(query, filters_list)

    return query.all()


def select_best_recipe(
    eligible_recipes: list[models.Recipe],
    last_cooked_dates: dict[UUID, datetime],
    selected_recipes: list[models.Recipe],
    selected_recipe_ids: set[UUID],
    weights: schemas.MealPlanScoringWeights,
    freshness_window_days: int = 30
) -> tuple[models.Recipe | None, float, float, float]:
    """
    Select the best recipe from eligible candidates based on scoring.

    Returns: (recipe, freshness_score, variety_score, combined_score)
    """
    if not eligible_recipes:
        return None, 0.0, 0.0, 0.0

    best_recipe = None
    best_score = -1.0
    best_freshness = 0.0
    best_variety = 0.0

    for recipe in eligible_recipes:
        combined, freshness, variety, _ = calculate_combined_score(
            recipe,
            last_cooked_dates,
            selected_recipes,
            selected_recipe_ids,
            weights,
            freshness_window_days
        )

        if combined > best_score:
            best_score = combined
            best_recipe = recipe
            best_freshness = freshness
            best_variety = variety

    return best_recipe, best_freshness, best_variety, best_score


def generate_meal_plan(
    db: Session,
    user_id: UUID,
    plan_request: schemas.MealPlanCreate
) -> models.MealPlan:
    """
    Generate a complete meal plan based on the request parameters.

    Steps:
    1. Create the MealPlan record
    2. Get eligible recipes based on constraints
    3. Get last cooked dates for freshness scoring
    4. For each day and classification, select the best recipe
    5. Handle pinned meals
    """
    # Generate name if not provided
    name = plan_request.name
    if not name:
        start_str = plan_request.start_date.strftime("%b %d, %Y")
        name = f"Week of {start_str}"

    # Create the meal plan
    config_dict = plan_request.config.model_dump() if plan_request.config else None
    db_plan = crud.create_meal_plan(
        db=db,
        user_id=user_id,
        name=name,
        start_date=plan_request.start_date,
        end_date=plan_request.end_date,
        config=config_dict
    )

    # Get constraints and scoring weights
    constraints = plan_request.config.constraints
    weights = plan_request.config.scoring_weights
    freshness_window = plan_request.config.freshness_window_days

    # Get eligible recipes
    eligible_recipes = get_eligible_recipes(db, user_id, constraints)

    if not eligible_recipes:
        # No recipes match constraints - return empty plan
        return db_plan

    # Get last cooked dates for all eligible recipes
    recipe_ids = [r.id for r in eligible_recipes]
    last_cooked_dates = crud.get_recipes_last_cooked_dates(db, recipe_ids, user_id)

    # Build pinned meals lookup: (date, classification) -> recipe_id
    pinned_lookup: dict[tuple[str, str], UUID] = {}
    for pinned in plan_request.pinned_meals:
        date_str = pinned.date.strftime("%Y-%m-%d")
        pinned_lookup[(date_str, pinned.classification.value)] = pinned.recipe_id

    # Track selected recipes for variety scoring
    selected_recipes: list[models.Recipe] = []
    selected_recipe_ids: set[UUID] = set()

    # Generate meals for each day
    current_date = plan_request.start_date
    while current_date <= plan_request.end_date:
        date_str = current_date.strftime("%Y-%m-%d")

        for classification_name, count in plan_request.meals_per_day.items():
            classification = models.MealClassification(classification_name)

            for _ in range(count):
                # Check if this meal is pinned
                pinned_recipe_id = pinned_lookup.get((date_str, classification_name))

                if pinned_recipe_id:
                    # Use pinned recipe
                    recipe = db.query(models.Recipe).filter(
                        models.Recipe.id == pinned_recipe_id
                    ).first()
                    is_pinned = True
                else:
                    # Select best recipe based on scoring
                    recipe, _, _, _ = select_best_recipe(
                        eligible_recipes,
                        last_cooked_dates,
                        selected_recipes,
                        selected_recipe_ids,
                        weights,
                        freshness_window
                    )
                    is_pinned = False

                if recipe:
                    # Create meal
                    db_meal = models.Meal(
                        user_id=user_id,
                        meal_plan_id=db_plan.id,
                        name=recipe.name,
                        status=models.MealStatus.PROPOSED,
                        classification=classification,
                        date=current_date,
                        pinned=is_pinned
                    )
                    db.add(db_meal)
                    db.flush()

                    # Create meal item
                    db_item = models.MealItem(
                        meal_id=db_meal.id,
                        recipe_id=recipe.id
                    )
                    db.add(db_item)

                    # Track for variety scoring
                    selected_recipes.append(recipe)
                    selected_recipe_ids.add(recipe.id)

        current_date += timedelta(days=1)

    db.commit()
    db.refresh(db_plan)
    return db_plan


def regenerate_meal(
    db: Session,
    plan_id: UUID,
    meal_id: UUID,
    user_id: UUID
) -> models.Meal | None:
    """
    Regenerate a single meal within a plan, selecting a new recipe.

    Only works on DRAFT plans and non-pinned meals.
    """
    # Get the plan
    db_plan = crud.get_meal_plan(db, plan_id, user_id)
    if not db_plan:
        return None

    if db_plan.status == models.MealPlanStatus.FINALIZED:
        raise ValueError("Cannot regenerate meals in a finalized plan")

    # Find the meal
    db_meal = None
    for meal in db_plan.meals:
        if meal.id == meal_id:
            db_meal = meal
            break

    if not db_meal:
        return None

    if db_meal.pinned:
        raise ValueError("Cannot regenerate a pinned meal")

    # Get config from plan
    config = schemas.MealPlanConfig(**(db_plan.config or {}))
    constraints = config.constraints
    weights = config.scoring_weights
    freshness_window = config.freshness_window_days

    # Get eligible recipes
    eligible_recipes = get_eligible_recipes(db, user_id, constraints)
    if not eligible_recipes:
        return db_meal  # No alternatives available

    # Get last cooked dates
    recipe_ids = [r.id for r in eligible_recipes]
    last_cooked_dates = crud.get_recipes_last_cooked_dates(db, recipe_ids, user_id)

    # Get other selected recipes in the plan for variety scoring
    selected_recipes: list[models.Recipe] = []
    selected_recipe_ids: set[UUID] = set()
    current_recipe_id = db_meal.items[0].recipe_id if db_meal.items else None

    for meal in db_plan.meals:
        if meal.id != meal_id and meal.items:
            recipe = meal.items[0].recipe
            if recipe:
                selected_recipes.append(recipe)
                selected_recipe_ids.add(recipe.id)

    # Exclude current recipe from selection
    if current_recipe_id:
        selected_recipe_ids.add(current_recipe_id)

    # Select new recipe
    new_recipe, _, _, _ = select_best_recipe(
        eligible_recipes,
        last_cooked_dates,
        selected_recipes,
        selected_recipe_ids,
        weights,
        freshness_window
    )

    if new_recipe:
        # Clear existing items
        db_meal.items.clear()

        # Update meal
        db_meal.name = new_recipe.name

        # Add new item
        db_item = models.MealItem(
            meal_id=db_meal.id,
            recipe_id=new_recipe.id
        )
        db.add(db_item)

        db.commit()
        db.refresh(db_meal)

    return db_meal


def pin_meal(
    db: Session,
    plan_id: UUID,
    meal_id: UUID,
    user_id: UUID,
    recipe_id: UUID | None = None
) -> models.Meal | None:
    """
    Pin a meal, optionally swapping to a specific recipe.
    """
    # Get the plan
    db_plan = crud.get_meal_plan(db, plan_id, user_id)
    if not db_plan:
        return None

    if db_plan.status == models.MealPlanStatus.FINALIZED:
        raise ValueError("Cannot modify meals in a finalized plan")

    # Find the meal
    db_meal = None
    for meal in db_plan.meals:
        if meal.id == meal_id:
            db_meal = meal
            break

    if not db_meal:
        return None

    # If recipe_id provided, swap the recipe
    if recipe_id:
        recipe = db.query(models.Recipe).filter(models.Recipe.id == recipe_id).first()
        if not recipe:
            raise ValueError("Recipe not found")

        # Clear existing items and add new one
        db_meal.items.clear()
        db_meal.name = recipe.name

        db_item = models.MealItem(
            meal_id=db_meal.id,
            recipe_id=recipe.id
        )
        db.add(db_item)

    # Mark as pinned
    db_meal.pinned = True

    db.commit()
    db.refresh(db_meal)
    return db_meal


def unpin_meal(
    db: Session,
    plan_id: UUID,
    meal_id: UUID,
    user_id: UUID
) -> models.Meal | None:
    """
    Unpin a meal.
    """
    # Get the plan
    db_plan = crud.get_meal_plan(db, plan_id, user_id)
    if not db_plan:
        return None

    if db_plan.status == models.MealPlanStatus.FINALIZED:
        raise ValueError("Cannot modify meals in a finalized plan")

    # Find the meal
    db_meal = None
    for meal in db_plan.meals:
        if meal.id == meal_id:
            db_meal = meal
            break

    if not db_meal:
        return None

    db_meal.pinned = False

    db.commit()
    db.refresh(db_meal)
    return db_meal


def select_recipe_weighted_by_freshness(
    db: Session,
    recipes: list[models.Recipe],
    user_id: UUID,
    freshness_window_days: int = 30
) -> models.Recipe | None:
    """
    Select a recipe from the list using freshness scores as weights for random selection.

    Recipes not cooked recently are more likely to be selected.
    Uses weighted random selection where the weight is the freshness score.

    Args:
        db: Database session
        recipes: List of candidate recipes
        user_id: User ID for querying cooked meals
        freshness_window_days: Window for freshness calculation (default 30)

    Returns:
        Selected recipe, or None if the list is empty
    """
    if not recipes:
        return None

    if len(recipes) == 1:
        return recipes[0]

    # Get last cooked dates for all recipes
    recipe_ids = [r.id for r in recipes]
    last_cooked_dates = crud.get_recipes_last_cooked_dates(db, recipe_ids, user_id)

    # Calculate freshness scores
    weights = []
    for recipe in recipes:
        score = calculate_freshness_score(
            recipe.id, last_cooked_dates, freshness_window_days
        )
        # Ensure minimum weight to avoid zero probability
        weights.append(max(score, 0.01))

    # Weighted random selection
    total_weight = sum(weights)
    r = random.random() * total_weight

    cumulative = 0.0
    for recipe, weight in zip(recipes, weights):
        cumulative += weight
        if r <= cumulative:
            return recipe

    # Fallback (should not reach here)
    return recipes[-1]


def get_meal_plan_with_scores(
    db: Session,
    plan_id: UUID,
    user_id: UUID
) -> dict | None:
    """
    Get a meal plan with freshness/variety scores for each meal.
    """
    db_plan = crud.get_meal_plan(db, plan_id, user_id)
    if not db_plan:
        return None

    # Get config
    config = schemas.MealPlanConfig(**(db_plan.config or {}))
    weights = config.scoring_weights
    freshness_window = config.freshness_window_days

    # Get all recipe IDs from meals
    recipe_ids = []
    recipes_map: dict[UUID, models.Recipe] = {}
    for meal in db_plan.meals:
        if meal.items:
            recipe = meal.items[0].recipe
            if recipe:
                recipe_ids.append(recipe.id)
                recipes_map[meal.id] = recipe

    # Get last cooked dates
    last_cooked_dates = crud.get_recipes_last_cooked_dates(db, recipe_ids, user_id)

    # Calculate scores for each meal
    meals_with_scores = []
    selected_recipes: list[models.Recipe] = []

    for meal in db_plan.meals:
        recipe = recipes_map.get(meal.id)

        if recipe:
            freshness = calculate_freshness_score(
                recipe.id, last_cooked_dates, freshness_window
            )
            variety = calculate_variety_score(recipe, selected_recipes)
            combined = (
                weights.freshness_weight * freshness +
                weights.variety_weight * variety
            )
            selected_recipes.append(recipe)
        else:
            freshness = None
            variety = None
            combined = None

        meals_with_scores.append({
            "meal": meal,
            "freshness_score": freshness,
            "variety_score": variety,
            "combined_score": combined
        })

    return {
        "plan": db_plan,
        "meals_with_scores": meals_with_scores
    }
