"""Rule for the three-letter acronym used to build document codes.

Every catalog entry (disciplines today, document types later) is
identified by the first three letters of its name, upper-cased and
stripped of accents: "Tubulação" -> "TUB", "Memória de Cálculo" -> "MEM".
"""

import re
import unicodedata

ACRONYM_PATTERN = re.compile(r"^[A-Z]{3}$")
ACRONYM_LENGTH = 3


def strip_accents(text: str) -> str:
    """Return the text with every accent removed ("Configuração" -> "Configuracao")."""
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(char for char in normalized if not unicodedata.combining(char))


def generate_acronym(name: str) -> str:
    """Build the acronym from the first three letters of the name.

    Spaces, digits and punctuation are ignored, so "Memória de Cálculo"
    yields "MEM". Returns fewer than three letters when the name is too
    short; validation of the final format is done by the model.
    """
    letters = [char for char in strip_accents(name) if char.isalpha()]
    return "".join(letters[:ACRONYM_LENGTH]).upper()


def is_valid_acronym(acronym: str) -> bool:
    """Tell whether the acronym is exactly three upper-case ASCII letters."""
    return bool(ACRONYM_PATTERN.match(acronym or ""))
