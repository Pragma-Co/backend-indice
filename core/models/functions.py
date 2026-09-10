"""Database functions used in index and constraint expressions."""

from django.db import models


class ImmutableUnaccent(models.Func):
    """`unaccent()` wrapped in an IMMUTABLE SQL function.

    The `unaccent(text)` shipped by the extension is only STABLE, because it
    resolves the dictionary through `search_path`, and PostgreSQL refuses to
    index a non-IMMUTABLE expression. Migration 0002 creates
    `immutable_unaccent(text)`, which pins the dictionary explicitly and can
    therefore be declared IMMUTABLE.
    """

    function = "immutable_unaccent"
    arity = 1
    output_field = models.TextField()
