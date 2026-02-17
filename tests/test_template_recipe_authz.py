"""Tests for templates and recipes authorization using AuthContext.

Tests written FIRST (TDD) - these will fail until the endpoints are migrated
to use get_auth_context instead of get_current_active_user.

Authorization rules being tested:

Templates (Shared Read):
- Any authenticated user can VIEW any template (no ownership check on reads).
- Only the OWNER can UPDATE or DELETE their template.
- An admin in admin mode can view, update, or delete ANY template.

Recipes (Shared Read):
- Any authenticated user can VIEW any recipe (no ownership check on reads).
- Only the OWNER can UPDATE or DELETE their recipe.
- An admin in admin mode can view, update, or delete ANY recipe.
- Comment ownership rules mirror the same pattern (author or admin mode).
"""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import crud, schemas, models


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def create_user_and_login(
    client: TestClient,
    db: Session,
    email: str,
    password: str = "password",
    is_admin: bool = False,
):
    """Create a user (if not exists), set admin flag if needed, return (user, headers)."""
    try:
        user_in = schemas.UserCreate(email=email, password=password)
        user = crud.create_user(db, user_in)
    except Exception:
        user = crud.get_user_by_email(db, email=email)

    if is_admin and not user.is_admin:
        user.is_admin = True
        db.add(user)
        db.commit()

    response = client.post(
        "/auth/token",
        data={"username": email, "password": password},
    )
    assert response.status_code == 200, f"Login failed for {email}: {response.json()}"
    token = response.json()["access_token"]
    return user, {"Authorization": f"Bearer {token}"}


def create_recipe_via_api(client: TestClient, headers: dict, name: str = "Test Recipe") -> dict:
    """Create a recipe via the API and return the response JSON."""
    recipe_data = {
        "core": {"name": name},
        "times": {},
        "nutrition": {},
        "components": [],
        "instructions": [],
    }
    response = client.post("/recipes/", json=recipe_data, headers=headers)
    assert response.status_code == 201, f"Recipe creation failed: {response.json()}"
    return response.json()


def create_recipe_direct(db: Session, user_id, name: str) -> models.Recipe:
    """Create a recipe directly in the DB."""
    recipe = models.Recipe(
        name=name,
        owner_id=user_id,
        description="Test description",
        instructions=[],
        components=[],
    )
    db.add(recipe)
    db.commit()
    db.refresh(recipe)
    return recipe


def create_template_direct(db: Session, user_id, name: str) -> models.MealTemplate:
    """Create a meal template directly in the DB."""
    template = models.MealTemplate(
        user_id=user_id,
        name=name,
        slots_checksum="abc123",
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


def create_comment_direct(db: Session, user_id, recipe_id, text: str = "A comment") -> models.Comment:
    """Create a comment directly in the DB."""
    comment = models.Comment(
        user_id=user_id,
        recipe_id=recipe_id,
        text=text,
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return comment


# ===========================================================================
# TEMPLATE TESTS
# ===========================================================================


# ---------------------------------------------------------------------------
# GET /meals/templates - shared read
# ---------------------------------------------------------------------------


def test_get_templates_any_user_can_list_all(client: TestClient, db: Session):
    """GET /meals/templates — any authenticated user can see all templates."""
    owner, owner_headers = create_user_and_login(
        client, db, "tpl_list_owner@example.com"
    )
    other, other_headers = create_user_and_login(
        client, db, "tpl_list_other@example.com"
    )

    template = create_template_direct(db, owner.id, "Owner Template For List")

    # The 'other' user (non-owner) should be able to list and see the template
    response = client.get("/meals/templates", headers=other_headers)
    assert response.status_code == 200

    template_ids = [t["id"] for t in response.json()]
    assert str(template.id) in template_ids, "Non-owner should see all templates"


# ---------------------------------------------------------------------------
# GET /meals/templates/{id} - shared read
# ---------------------------------------------------------------------------


def test_get_template_by_id_non_owner_can_view(client: TestClient, db: Session):
    """GET /meals/templates/{id} — non-owner can view any template."""
    owner, owner_headers = create_user_and_login(
        client, db, "tpl_get_owner@example.com"
    )
    other, other_headers = create_user_and_login(
        client, db, "tpl_get_other@example.com"
    )

    template = create_template_direct(db, owner.id, "Owner Template For Get")

    response = client.get(f"/meals/templates/{template.id}", headers=other_headers)
    assert response.status_code == 200
    assert response.json()["id"] == str(template.id)


# ---------------------------------------------------------------------------
# PUT /meals/templates/{id} - ownership required
# ---------------------------------------------------------------------------


def test_put_template_non_owner_gets_403(client: TestClient, db: Session):
    """PUT /meals/templates/{id} — non-owner gets 403."""
    owner, owner_headers = create_user_and_login(
        client, db, "tpl_put403_owner@example.com"
    )
    other, other_headers = create_user_and_login(
        client, db, "tpl_put403_other@example.com"
    )

    template = create_template_direct(db, owner.id, "Owner Template For Put")

    response = client.put(
        f"/meals/templates/{template.id}",
        json={"name": "Hacked Template"},
        headers=other_headers,
    )
    assert response.status_code == 403


def test_put_template_owner_succeeds(client: TestClient, db: Session):
    """PUT /meals/templates/{id} — owner can update their template."""
    owner, owner_headers = create_user_and_login(
        client, db, "tpl_put_owner@example.com"
    )

    template = create_template_direct(db, owner.id, "Owner Template To Update")

    response = client.put(
        f"/meals/templates/{template.id}",
        json={"name": "Updated Template Name"},
        headers=owner_headers,
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Updated Template Name"


def test_put_template_admin_mode_succeeds(client: TestClient, db: Session):
    """PUT /meals/templates/{id} with X-Admin-Mode: true — admin can update any template."""
    owner, _ = create_user_and_login(client, db, "tpl_putadmin_owner@example.com")
    admin, admin_base_headers = create_user_and_login(
        client, db, "tpl_putadmin_admin@example.com", is_admin=True
    )
    admin_headers = {**admin_base_headers, "X-Admin-Mode": "true"}

    template = create_template_direct(db, owner.id, "Template For Admin Update")

    response = client.put(
        f"/meals/templates/{template.id}",
        json={"name": "Admin Updated Template"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Admin Updated Template"


def test_put_template_admin_without_admin_mode_gets_403(client: TestClient, db: Session):
    """PUT /meals/templates/{id} — admin without X-Admin-Mode header is subject to ownership check."""
    owner, _ = create_user_and_login(client, db, "tpl_putadmin_nomode_owner@example.com")
    admin, admin_headers = create_user_and_login(
        client, db, "tpl_putadmin_nomode_admin@example.com", is_admin=True
    )
    # No X-Admin-Mode header — admin operates in user mode, subject to ownership checks
    template = create_template_direct(db, owner.id, "Template For Admin No-Mode Update")

    response = client.put(
        f"/meals/templates/{template.id}",
        json={"name": "Should Fail"},
        headers=admin_headers,
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# DELETE /meals/templates/{id} - ownership required
# ---------------------------------------------------------------------------


def test_delete_template_non_owner_gets_403(client: TestClient, db: Session):
    """DELETE /meals/templates/{id} — non-owner gets 403."""
    owner, owner_headers = create_user_and_login(
        client, db, "tpl_del403_owner@example.com"
    )
    other, other_headers = create_user_and_login(
        client, db, "tpl_del403_other@example.com"
    )

    template = create_template_direct(db, owner.id, "Owner Template For Delete Reject")

    response = client.delete(
        f"/meals/templates/{template.id}", headers=other_headers
    )
    assert response.status_code == 403


def test_delete_template_owner_succeeds(client: TestClient, db: Session):
    """DELETE /meals/templates/{id} — owner can delete their template."""
    owner, owner_headers = create_user_and_login(
        client, db, "tpl_del_owner@example.com"
    )

    template = create_template_direct(db, owner.id, "Owner Template To Delete")

    response = client.delete(
        f"/meals/templates/{template.id}", headers=owner_headers
    )
    assert response.status_code == 204


def test_delete_template_admin_mode_succeeds(client: TestClient, db: Session):
    """DELETE /meals/templates/{id} with X-Admin-Mode: true — admin can delete any template."""
    owner, _ = create_user_and_login(client, db, "tpl_deladmin_owner@example.com")
    admin, admin_base_headers = create_user_and_login(
        client, db, "tpl_deladmin_admin@example.com", is_admin=True
    )
    admin_headers = {**admin_base_headers, "X-Admin-Mode": "true"}

    template = create_template_direct(db, owner.id, "Template For Admin Delete")

    response = client.delete(
        f"/meals/templates/{template.id}", headers=admin_headers
    )
    assert response.status_code == 204

    # Confirm it's gone (admin can still check)
    get_response = client.get(
        f"/meals/templates/{template.id}", headers=admin_headers
    )
    assert get_response.status_code == 404


def test_delete_template_admin_without_admin_mode_gets_403(client: TestClient, db: Session):
    """DELETE /meals/templates/{id} — admin without X-Admin-Mode header is subject to ownership check."""
    owner, _ = create_user_and_login(
        client, db, "tpl_deladmin_nomode_owner@example.com"
    )
    admin, admin_headers = create_user_and_login(
        client, db, "tpl_deladmin_nomode_admin@example.com", is_admin=True
    )
    # No X-Admin-Mode header — admin operates in user mode, subject to ownership checks
    template = create_template_direct(db, owner.id, "Template For Admin No-Mode Delete")

    response = client.delete(
        f"/meals/templates/{template.id}", headers=admin_headers
    )
    assert response.status_code == 403


# ===========================================================================
# RECIPE TESTS
# ===========================================================================


# ---------------------------------------------------------------------------
# GET /recipes - shared read
# ---------------------------------------------------------------------------


def test_get_recipes_any_user_can_list_all(client: TestClient, db: Session):
    """GET /recipes — any authenticated user can see all recipes."""
    owner, _ = create_user_and_login(client, db, "rcp_list_owner@example.com")
    other, other_headers = create_user_and_login(
        client, db, "rcp_list_other@example.com"
    )

    recipe = create_recipe_direct(db, owner.id, "Owner Recipe For List")

    response = client.get("/recipes/", headers=other_headers)
    assert response.status_code == 200

    recipe_ids = [r["core"]["id"] for r in response.json()]
    assert str(recipe.id) in recipe_ids, "Non-owner should see all recipes"


# ---------------------------------------------------------------------------
# GET /recipes/{id} - shared read
# ---------------------------------------------------------------------------


def test_get_recipe_by_id_non_owner_can_view(client: TestClient, db: Session):
    """GET /recipes/{id} — non-owner can view any recipe."""
    owner, _ = create_user_and_login(client, db, "rcp_get_owner@example.com")
    other, other_headers = create_user_and_login(
        client, db, "rcp_get_other@example.com"
    )

    recipe = create_recipe_direct(db, owner.id, "Owner Recipe For Get")

    response = client.get(f"/recipes/{recipe.id}", headers=other_headers)
    assert response.status_code == 200
    assert response.json()["core"]["id"] == str(recipe.id)


# ---------------------------------------------------------------------------
# PUT /recipes/{id} - ownership required
# ---------------------------------------------------------------------------


def test_put_recipe_non_owner_gets_403(client: TestClient, db: Session):
    """PUT /recipes/{id} — non-owner gets 403."""
    owner, _ = create_user_and_login(client, db, "rcp_put403_owner@example.com")
    other, other_headers = create_user_and_login(
        client, db, "rcp_put403_other@example.com"
    )

    recipe = create_recipe_direct(db, owner.id, "Owner Recipe For Put Reject")

    update_data = {
        "core": {"name": "Hacked Recipe"},
        "times": {},
        "nutrition": {},
        "components": [],
        "instructions": [],
    }
    response = client.put(
        f"/recipes/{recipe.id}", json=update_data, headers=other_headers
    )
    assert response.status_code == 403


def test_put_recipe_owner_succeeds(client: TestClient, db: Session):
    """PUT /recipes/{id} — owner can update their recipe."""
    owner, owner_headers = create_user_and_login(
        client, db, "rcp_put_owner@example.com"
    )

    recipe = create_recipe_direct(db, owner.id, "Owner Recipe To Update")

    update_data = {
        "core": {"name": "Updated Recipe Name"},
        "times": {},
        "nutrition": {},
        "components": [],
        "instructions": [],
    }
    response = client.put(
        f"/recipes/{recipe.id}", json=update_data, headers=owner_headers
    )
    assert response.status_code == 200
    assert response.json()["core"]["name"] == "Updated Recipe Name"


def test_put_recipe_admin_mode_succeeds(client: TestClient, db: Session):
    """PUT /recipes/{id} with X-Admin-Mode: true — admin can update any recipe."""
    owner, _ = create_user_and_login(client, db, "rcp_putadmin_owner@example.com")
    admin, admin_base_headers = create_user_and_login(
        client, db, "rcp_putadmin_admin@example.com", is_admin=True
    )
    admin_headers = {**admin_base_headers, "X-Admin-Mode": "true"}

    recipe = create_recipe_direct(db, owner.id, "Recipe For Admin Update")

    update_data = {
        "core": {"name": "Admin Updated Recipe"},
        "times": {},
        "nutrition": {},
        "components": [],
        "instructions": [],
    }
    response = client.put(
        f"/recipes/{recipe.id}", json=update_data, headers=admin_headers
    )
    assert response.status_code == 200
    assert response.json()["core"]["name"] == "Admin Updated Recipe"


def test_put_recipe_admin_without_admin_mode_gets_403(client: TestClient, db: Session):
    """PUT /recipes/{id} — admin without X-Admin-Mode header is subject to ownership check."""
    owner, _ = create_user_and_login(
        client, db, "rcp_putadmin_nomode_owner@example.com"
    )
    admin, admin_headers = create_user_and_login(
        client, db, "rcp_putadmin_nomode_admin@example.com", is_admin=True
    )
    # No X-Admin-Mode header — admin operates in user mode, subject to ownership checks
    recipe = create_recipe_direct(db, owner.id, "Recipe For Admin No-Mode Update")

    update_data = {
        "core": {"name": "Should Fail"},
        "times": {},
        "nutrition": {},
        "components": [],
        "instructions": [],
    }
    response = client.put(
        f"/recipes/{recipe.id}", json=update_data, headers=admin_headers
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# DELETE /recipes/{id} - ownership required
# ---------------------------------------------------------------------------


def test_delete_recipe_non_owner_gets_403(client: TestClient, db: Session):
    """DELETE /recipes/{id} — non-owner gets 403."""
    owner, _ = create_user_and_login(client, db, "rcp_del403_owner@example.com")
    other, other_headers = create_user_and_login(
        client, db, "rcp_del403_other@example.com"
    )

    recipe = create_recipe_direct(db, owner.id, "Owner Recipe For Delete Reject")

    response = client.delete(f"/recipes/{recipe.id}", headers=other_headers)
    assert response.status_code == 403


def test_delete_recipe_owner_succeeds(client: TestClient, db: Session):
    """DELETE /recipes/{id} — owner can delete their recipe."""
    owner, owner_headers = create_user_and_login(
        client, db, "rcp_del_owner@example.com"
    )

    recipe = create_recipe_direct(db, owner.id, "Owner Recipe To Delete")

    response = client.delete(f"/recipes/{recipe.id}", headers=owner_headers)
    assert response.status_code == 200


def test_delete_recipe_admin_mode_succeeds(client: TestClient, db: Session):
    """DELETE /recipes/{id} with X-Admin-Mode: true — admin can delete any recipe."""
    owner, _ = create_user_and_login(client, db, "rcp_deladmin_owner@example.com")
    admin, admin_base_headers = create_user_and_login(
        client, db, "rcp_deladmin_admin@example.com", is_admin=True
    )
    admin_headers = {**admin_base_headers, "X-Admin-Mode": "true"}

    recipe = create_recipe_direct(db, owner.id, "Recipe For Admin Delete")

    response = client.delete(f"/recipes/{recipe.id}", headers=admin_headers)
    assert response.status_code == 200

    # Confirm it's gone
    get_response = client.get(f"/recipes/{recipe.id}", headers=admin_headers)
    assert get_response.status_code == 404


def test_delete_recipe_admin_without_admin_mode_gets_403(client: TestClient, db: Session):
    """DELETE /recipes/{id} — admin without X-Admin-Mode header is subject to ownership check."""
    owner, _ = create_user_and_login(
        client, db, "rcp_deladmin_nomode_owner@example.com"
    )
    admin, admin_headers = create_user_and_login(
        client, db, "rcp_deladmin_nomode_admin@example.com", is_admin=True
    )
    # No X-Admin-Mode header — admin operates in user mode, subject to ownership checks
    recipe = create_recipe_direct(db, owner.id, "Recipe For Admin No-Mode Delete")

    response = client.delete(f"/recipes/{recipe.id}", headers=admin_headers)
    assert response.status_code == 403


# ===========================================================================
# COMMENT TESTS
# ===========================================================================


# ---------------------------------------------------------------------------
# PUT /recipes/{id}/comments/{comment_id} - author or admin mode only
# ---------------------------------------------------------------------------


def test_put_comment_non_author_gets_403(client: TestClient, db: Session):
    """PUT comment — non-author gets 403."""
    author, author_headers = create_user_and_login(
        client, db, "cmt_put403_author@example.com"
    )
    other, other_headers = create_user_and_login(
        client, db, "cmt_put403_other@example.com"
    )

    recipe = create_recipe_direct(db, author.id, "Recipe For Comment Put Reject")
    comment = create_comment_direct(db, author.id, recipe.id, "Author comment text")

    response = client.put(
        f"/recipes/{recipe.id}/comments/{comment.id}",
        json={"text": "Hacked comment"},
        headers=other_headers,
    )
    assert response.status_code == 403


def test_put_comment_author_succeeds(client: TestClient, db: Session):
    """PUT comment — author can update their own comment."""
    author, author_headers = create_user_and_login(
        client, db, "cmt_put_author@example.com"
    )

    recipe = create_recipe_direct(db, author.id, "Recipe For Comment Put")
    comment = create_comment_direct(db, author.id, recipe.id, "Original comment")

    response = client.put(
        f"/recipes/{recipe.id}/comments/{comment.id}",
        json={"text": "Updated comment text"},
        headers=author_headers,
    )
    assert response.status_code == 200
    assert response.json()["text"] == "Updated comment text"


def test_put_comment_admin_mode_succeeds(client: TestClient, db: Session):
    """PUT comment with X-Admin-Mode: true — admin can update any comment."""
    author, _ = create_user_and_login(client, db, "cmt_putadmin_author@example.com")
    admin, admin_base_headers = create_user_and_login(
        client, db, "cmt_putadmin_admin@example.com", is_admin=True
    )
    admin_headers = {**admin_base_headers, "X-Admin-Mode": "true"}

    recipe = create_recipe_direct(db, author.id, "Recipe For Admin Comment Update")
    comment = create_comment_direct(db, author.id, recipe.id, "Comment for admin")

    response = client.put(
        f"/recipes/{recipe.id}/comments/{comment.id}",
        json={"text": "Admin updated comment"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["text"] == "Admin updated comment"


def test_put_comment_admin_without_admin_mode_gets_403(client: TestClient, db: Session):
    """PUT comment — admin without X-Admin-Mode header is subject to authorship check."""
    author, _ = create_user_and_login(
        client, db, "cmt_putadmin_nomode_author@example.com"
    )
    admin, admin_headers = create_user_and_login(
        client, db, "cmt_putadmin_nomode_admin@example.com", is_admin=True
    )
    # No X-Admin-Mode header — admin operates in user mode, subject to authorship checks
    recipe = create_recipe_direct(db, author.id, "Recipe For Admin No-Mode Comment Update")
    comment = create_comment_direct(
        db, author.id, recipe.id, "Comment for admin no-mode"
    )

    response = client.put(
        f"/recipes/{recipe.id}/comments/{comment.id}",
        json={"text": "Should fail"},
        headers=admin_headers,
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# DELETE /recipes/{id}/comments/{comment_id} - author or admin mode only
# ---------------------------------------------------------------------------


def test_delete_comment_non_author_gets_403(client: TestClient, db: Session):
    """DELETE comment — non-author gets 403."""
    author, _ = create_user_and_login(client, db, "cmt_del403_author@example.com")
    other, other_headers = create_user_and_login(
        client, db, "cmt_del403_other@example.com"
    )

    recipe = create_recipe_direct(db, author.id, "Recipe For Comment Delete Reject")
    comment = create_comment_direct(db, author.id, recipe.id, "Author comment for delete")

    response = client.delete(
        f"/recipes/{recipe.id}/comments/{comment.id}", headers=other_headers
    )
    assert response.status_code == 403


def test_delete_comment_author_succeeds(client: TestClient, db: Session):
    """DELETE comment — author can delete their own comment."""
    author, author_headers = create_user_and_login(
        client, db, "cmt_del_author@example.com"
    )

    recipe = create_recipe_direct(db, author.id, "Recipe For Comment Delete")
    comment = create_comment_direct(db, author.id, recipe.id, "Comment to delete")

    response = client.delete(
        f"/recipes/{recipe.id}/comments/{comment.id}", headers=author_headers
    )
    assert response.status_code == 204


def test_delete_comment_admin_mode_succeeds(client: TestClient, db: Session):
    """DELETE comment with X-Admin-Mode: true — admin can delete any comment."""
    author, _ = create_user_and_login(client, db, "cmt_deladmin_author@example.com")
    admin, admin_base_headers = create_user_and_login(
        client, db, "cmt_deladmin_admin@example.com", is_admin=True
    )
    admin_headers = {**admin_base_headers, "X-Admin-Mode": "true"}

    recipe = create_recipe_direct(db, author.id, "Recipe For Admin Comment Delete")
    comment = create_comment_direct(
        db, author.id, recipe.id, "Comment for admin to delete"
    )

    response = client.delete(
        f"/recipes/{recipe.id}/comments/{comment.id}", headers=admin_headers
    )
    assert response.status_code == 204


def test_delete_comment_admin_without_admin_mode_gets_403(client: TestClient, db: Session):
    """DELETE comment — admin without X-Admin-Mode header is subject to authorship check."""
    author, _ = create_user_and_login(
        client, db, "cmt_deladmin_nomode_author@example.com"
    )
    admin, admin_headers = create_user_and_login(
        client, db, "cmt_deladmin_nomode_admin@example.com", is_admin=True
    )
    # No X-Admin-Mode header — admin operates in user mode, subject to authorship checks
    recipe = create_recipe_direct(db, author.id, "Recipe For Admin No-Mode Comment Delete")
    comment = create_comment_direct(
        db, author.id, recipe.id, "Comment for admin no-mode delete"
    )

    response = client.delete(
        f"/recipes/{recipe.id}/comments/{comment.id}", headers=admin_headers
    )
    assert response.status_code == 403
