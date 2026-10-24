from django.db import migrations

CREATE_ENGLISH_CONFIG = """
    CREATE TEXT SEARCH CONFIGURATION english_unaccent (COPY = english);
    ALTER TEXT SEARCH CONFIGURATION english_unaccent
        ALTER MAPPING FOR hword, hword_part, word WITH unaccent, english_stem;
"""

DROP_ENGLISH_CONFIG = "DROP TEXT SEARCH CONFIGURATION IF EXISTS english_unaccent;"

REBUILD_VECTORS = """
    UPDATE document_content SET search_vector =
        setweight(to_tsvector('portuguese_unaccent', array_to_string(thematic_tags, ' ')), 'B')
        || setweight(to_tsvector('portuguese_unaccent', content), 'C')
        || setweight(to_tsvector('english_unaccent', content), 'C');
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0021_remove_project_disciplines")]

    operations = [
        migrations.RunSQL(CREATE_ENGLISH_CONFIG, DROP_ENGLISH_CONFIG),
        migrations.RunSQL(REBUILD_VECTORS, migrations.RunSQL.noop),
    ]
