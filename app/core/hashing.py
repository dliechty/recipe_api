import hashlib
import json
from typing import Any


def calculate_recipe_checksum(recipe_data: dict) -> str:
    """
    Calculates a SHA256 checksum for the provided recipe data.
    Ensures deterministic output by sorting keys and handling specific types.
    """

    # helper to ensure we are serializing consistently
    def default_serializer(obj: Any) -> Any:
        # Handle objects that are not natively JSON serializable if any remain
        # For our use case (Pydantic dumps), we mostly get standard types,
        # but just in case UUID or Datetime slips through (though model_dump usually handles them if configured)
        return str(obj)

    # We only care about the content fields for the checksum.
    # Metadata like 'updated_at' obviously changes on update so shouldn't be part of the content hash
    # if we are diffing "content".
    # However, the strategy is: we reconstruct the "new state" from the input.
    # The input to create/update usually lacks system-managed fields like updated_at.

    # We should normalize the dictionary.
    # Sorting keys is crucial.
    serialized = json.dumps(
        recipe_data, sort_keys=True, default=default_serializer, ensure_ascii=True
    )

    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
