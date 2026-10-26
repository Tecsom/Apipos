"""Coercion helpers shared by services and controllers."""


def truthy(value):
    """Coerce a setting value (bool / str / number) to a boolean.

    Accepts true/1/"yes"/"on"/"si"/"sí" (case-insensitive) as True.
    """
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on', 'si', 'sí')
