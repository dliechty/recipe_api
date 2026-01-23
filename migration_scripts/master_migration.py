import sys
import os
import argparse

# Add the project root to sys.path
sys.path.append(os.getcwd())

from migration_scripts.purge_recipes import purge_recipes
from migration_scripts.purge_meals import purge_meals
from migration_scripts.migrate_access_recipes import migrate_recipes
from migration_scripts.migrate_access_meals import migrate_meals


def purge_all():
    print("=== PURGING ALL DATA ===")
    # Order matters: dependent data first
    # Meals depend on Recipes/Templates
    purge_meals()
    # Recipes depend on Ingredients
    purge_recipes()
    print("=== PURGE ALL COMPLETE ===")


def migrate_all():
    print("=== MIGRATING ALL DATA ===")
    # Order matters: dependencies first
    # Recipes first (needed by Meals)
    migrate_recipes()
    # Meals next
    migrate_meals()
    print("=== MIGRATE ALL COMPLETE ===")


def main():
    parser = argparse.ArgumentParser(description="Master Migration Script")
    parser.add_argument(
        "action",
        choices=[
            "purge-all",
            "migrate-all",
            "purge-recipes",
            "purge-meals",
            "migrate-recipes",
            "migrate-meals",
        ],
        help="Action to perform",
    )

    args = parser.parse_args()

    if args.action == "purge-all":
        purge_all()
    elif args.action == "migrate-all":
        migrate_all()
    elif args.action == "purge-recipes":
        purge_recipes()
    elif args.action == "purge-meals":
        purge_meals()
    elif args.action == "migrate-recipes":
        migrate_recipes()
    elif args.action == "migrate-meals":
        migrate_meals()


if __name__ == "__main__":
    main()
