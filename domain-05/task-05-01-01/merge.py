def merge_facts(existing: dict, new: dict) -> dict:
    for key, value in new.items():
        if not value:
            continue
        if isinstance(value, dict) and isinstance(existing.get(key), dict):
            existing[key].update(value)
        elif isinstance(value, list) and isinstance(existing.get(key), list):
            existing_ids = {
                item.get("order_id") or item.get("payment_id")
                for item in existing[key]
            }
            for item in value:
                item_id = item.get("order_id") or item.get("payment_id")
                if item_id not in existing_ids:
                    existing[key].append(item)
        else:
            existing[key] = value
    return existing
