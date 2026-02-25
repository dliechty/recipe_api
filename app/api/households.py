from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from uuid import UUID
from app.db.session import get_db
from app import models, schemas
from app.api import auth

router = APIRouter()
users_router = APIRouter()


# --- Helper Functions ---


def get_household_or_404(db: Session, household_id: UUID) -> models.Household:
    household = (
        db.query(models.Household).filter(models.Household.id == household_id).first()
    )
    if not household:
        raise HTTPException(status_code=404, detail="Household not found")
    return household


def get_membership(
    db: Session, household_id: UUID, user_id: UUID
) -> models.HouseholdMembership | None:
    return (
        db.query(models.HouseholdMembership)
        .filter(
            models.HouseholdMembership.household_id == household_id,
            models.HouseholdMembership.user_id == user_id,
        )
        .first()
    )


def require_membership(
    db: Session, household_id: UUID, user_id: UUID, ctx: auth.AuthContext
):
    """Raise 403 if user is not a member (admins bypass)."""
    if ctx.is_admin_mode:
        return
    membership = get_membership(db, household_id, user_id)
    if not membership:
        raise HTTPException(status_code=403, detail="Not a member of this household")


def require_creator_or_admin(household: models.Household, ctx: auth.AuthContext):
    """Raise 403 if user is not the creator and not admin."""
    if ctx.is_admin_mode:
        return
    if household.created_by != ctx.effective_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")


# --- Household CRUD ---


@router.post(
    "",
    response_model=schemas.Household,
    status_code=status.HTTP_201_CREATED,
)
def create_household(
    household_in: schemas.HouseholdCreate,
    db: Session = Depends(get_db),
    ctx: auth.AuthContext = Depends(auth.get_auth_context),
):
    db_household = models.Household(
        name=household_in.name,
        created_by=ctx.effective_user.id,
    )
    db.add(db_household)
    db.flush()

    # Auto-create membership for the creator
    membership = models.HouseholdMembership(
        household_id=db_household.id,
        user_id=ctx.effective_user.id,
    )
    db.add(membership)
    db.commit()
    db.refresh(db_household)
    return db_household


@router.get("", response_model=List[schemas.Household])
def list_households(
    skip: int = Query(
        default=0, ge=0, description="Number of records to skip for pagination"
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=1000,
        description="Maximum number of records to return (1-1000)",
    ),
    db: Session = Depends(get_db),
    ctx: auth.AuthContext = Depends(auth.get_auth_context),
):
    if ctx.is_admin_mode:
        query = db.query(models.Household)
    else:
        query = (
            db.query(models.Household)
            .join(models.HouseholdMembership)
            .filter(models.HouseholdMembership.user_id == ctx.effective_user.id)
        )
    return query.offset(skip).limit(limit).all()


@router.get("/{household_id}", response_model=schemas.Household)
def get_household(
    household_id: UUID,
    db: Session = Depends(get_db),
    ctx: auth.AuthContext = Depends(auth.get_auth_context),
):
    household = get_household_or_404(db, household_id)
    require_membership(db, household_id, ctx.effective_user.id, ctx)
    return household


@router.patch("/{household_id}", response_model=schemas.Household)
def update_household(
    household_id: UUID,
    household_in: schemas.HouseholdUpdate,
    db: Session = Depends(get_db),
    ctx: auth.AuthContext = Depends(auth.get_auth_context),
):
    household = get_household_or_404(db, household_id)
    require_creator_or_admin(household, ctx)

    if household_in.name is not None:
        household.name = household_in.name

    db.commit()
    db.refresh(household)
    return household


@router.delete("/{household_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_household(
    household_id: UUID,
    db: Session = Depends(get_db),
    ctx: auth.AuthContext = Depends(auth.get_auth_context),
):
    household = get_household_or_404(db, household_id)
    require_creator_or_admin(household, ctx)

    # Soft-unlink meals: set household_id = NULL
    db.query(models.Meal).filter(models.Meal.household_id == household_id).update(
        {models.Meal.household_id: None}
    )

    db.delete(household)
    db.commit()
    return None


# --- Membership Endpoints ---


@router.post(
    "/{household_id}/join",
    response_model=schemas.HouseholdMember,
    status_code=status.HTTP_201_CREATED,
)
def join_household(
    household_id: UUID,
    db: Session = Depends(get_db),
    ctx: auth.AuthContext = Depends(auth.get_auth_context),
):
    get_household_or_404(db, household_id)

    existing = get_membership(db, household_id, ctx.effective_user.id)
    if existing:
        raise HTTPException(
            status_code=409, detail="Already a member of this household"
        )

    membership = models.HouseholdMembership(
        household_id=household_id,
        user_id=ctx.effective_user.id,
    )
    db.add(membership)
    db.commit()
    db.refresh(membership)
    return membership


@router.delete("/{household_id}/leave", status_code=status.HTTP_204_NO_CONTENT)
def leave_household(
    household_id: UUID,
    db: Session = Depends(get_db),
    ctx: auth.AuthContext = Depends(auth.get_auth_context),
):
    get_household_or_404(db, household_id)

    membership = get_membership(db, household_id, ctx.effective_user.id)
    if not membership:
        raise HTTPException(status_code=404, detail="Not a member of this household")

    db.delete(membership)
    db.commit()
    return None


@router.get("/{household_id}/members", response_model=List[schemas.HouseholdMember])
def list_members(
    household_id: UUID,
    db: Session = Depends(get_db),
    ctx: auth.AuthContext = Depends(auth.get_auth_context),
):
    get_household_or_404(db, household_id)
    require_membership(db, household_id, ctx.effective_user.id, ctx)

    return (
        db.query(models.HouseholdMembership)
        .filter(models.HouseholdMembership.household_id == household_id)
        .all()
    )


@router.delete(
    "/{household_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_member(
    household_id: UUID,
    user_id: UUID,
    db: Session = Depends(get_db),
    ctx: auth.AuthContext = Depends(auth.get_auth_context),
):
    household = get_household_or_404(db, household_id)
    require_creator_or_admin(household, ctx)

    # Cannot remove yourself this way (use /leave instead)
    if user_id == ctx.effective_user.id:
        raise HTTPException(
            status_code=400,
            detail="Cannot remove yourself; use /leave instead",
        )

    membership = get_membership(db, household_id, user_id)
    if not membership:
        raise HTTPException(
            status_code=404, detail="User is not a member of this household"
        )

    db.delete(membership)
    db.commit()
    return None


# --- Primary Household (mounted under /users) ---


@users_router.patch("/me/primary-household")
def set_primary_household(
    body: schemas.PrimaryHouseholdUpdate,
    db: Session = Depends(get_db),
    ctx: auth.AuthContext = Depends(auth.get_auth_context),
):
    user_id = ctx.effective_user.id

    if body.household_id is not None:
        # Validate membership
        membership = get_membership(db, body.household_id, user_id)
        if not membership:
            raise HTTPException(
                status_code=403,
                detail="Not a member of this household",
            )

        # Clear all is_primary flags for this user
        db.query(models.HouseholdMembership).filter(
            models.HouseholdMembership.user_id == user_id,
        ).update({models.HouseholdMembership.is_primary: False})

        # Set the chosen one as primary
        membership.is_primary = True
        db.commit()
        return {"message": "Primary household updated"}
    else:
        # Clear all is_primary flags
        db.query(models.HouseholdMembership).filter(
            models.HouseholdMembership.user_id == user_id,
        ).update({models.HouseholdMembership.is_primary: False})
        db.commit()
        return {"message": "Primary household cleared"}


# --- Template Exclusion Endpoints ---


@router.get(
    "/{household_id}/disabled-templates",
    response_model=List[schemas.HouseholdTemplateExclusion],
)
def list_disabled_templates(
    household_id: UUID,
    db: Session = Depends(get_db),
    ctx: auth.AuthContext = Depends(auth.get_auth_context),
):
    get_household_or_404(db, household_id)
    require_membership(db, household_id, ctx.effective_user.id, ctx)

    return (
        db.query(models.HouseholdTemplateExclusion)
        .filter(models.HouseholdTemplateExclusion.household_id == household_id)
        .all()
    )


@router.post(
    "/{household_id}/disabled-templates",
    response_model=schemas.HouseholdTemplateExclusion,
    status_code=status.HTTP_201_CREATED,
)
def disable_template(
    household_id: UUID,
    body: schemas.HouseholdTemplateExclusionCreate,
    db: Session = Depends(get_db),
    ctx: auth.AuthContext = Depends(auth.get_auth_context),
):
    get_household_or_404(db, household_id)
    require_membership(db, household_id, ctx.effective_user.id, ctx)

    # Validate template exists
    template = (
        db.query(models.MealTemplate)
        .filter(models.MealTemplate.id == body.template_id)
        .first()
    )
    if not template:
        raise HTTPException(status_code=404, detail="Meal template not found")

    # Check if already excluded
    existing = (
        db.query(models.HouseholdTemplateExclusion)
        .filter(
            models.HouseholdTemplateExclusion.household_id == household_id,
            models.HouseholdTemplateExclusion.template_id == body.template_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail="Template is already disabled for this household",
        )

    exclusion = models.HouseholdTemplateExclusion(
        household_id=household_id,
        template_id=body.template_id,
    )
    db.add(exclusion)
    db.commit()
    db.refresh(exclusion)
    return exclusion


@router.delete(
    "/{household_id}/disabled-templates/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def enable_template(
    household_id: UUID,
    template_id: UUID,
    db: Session = Depends(get_db),
    ctx: auth.AuthContext = Depends(auth.get_auth_context),
):
    get_household_or_404(db, household_id)
    require_membership(db, household_id, ctx.effective_user.id, ctx)

    exclusion = (
        db.query(models.HouseholdTemplateExclusion)
        .filter(
            models.HouseholdTemplateExclusion.household_id == household_id,
            models.HouseholdTemplateExclusion.template_id == template_id,
        )
        .first()
    )
    if not exclusion:
        raise HTTPException(
            status_code=404,
            detail="Template exclusion not found",
        )

    db.delete(exclusion)
    db.commit()
    return None
