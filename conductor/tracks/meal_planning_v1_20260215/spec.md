# Track Specification: Meal Planning Enhancements

## Overview
This track aims to evolve the meal planning capabilities of the Recipe API. Key improvements include better status management for meals, a recommendation/generation engine that favors "stale" recipes, and more flexible scheduling.

## Functional Requirements
- **Rich Status Tracking:** Extend the `Meal` status to include: `upcoming`, `shopped-for`, `cooked`, `cancelled`, `leftovers`.
- **Recency Awareness:** Track when a recipe was last cooked to support variety in meal planning.
- **Priority System:** Allow users to prioritize certain recipes or meals.
- **Meal Set Generation:** Generate a list of "Pending Meals" (drafts) based on user preferences, priority, and recency.
- **Scheduling:** Transition "Pending Meals" into a calendar schedule.

## Technical Requirements
- **Schema Updates:**
    - `Recipe` table: Add `last_cooked_at` (DateTime).
    - `Meal` table: Update `status` enum and add `priority` (Integer).
- **CRUD Enhancements:** Update CRUD operations to handle the new status and priority fields.
- **Generation Logic:** Create a service or utility function that ranks recipes based on `(priority * weight) + (time_since_last_cooked * weight)`.

## User Stories
- As a home cook, I want to see which recipes I haven't made in a while so I can maintain variety in our family meals.
- As a home cook, I want to mark a meal as "shopped-for" so I know I have the ingredients ready.
- As a home cook, I want the system to suggest 5 meals for next week based on our favorites and what's "due" to be cooked.
