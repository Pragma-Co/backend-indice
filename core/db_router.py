TOMBSTONE_ALIAS = "tombstone"
TOMBSTONE_APP_LABEL = "core"
TOMBSTONE_MODEL_NAME = "excludedidentifier"


def is_tombstone_model(model):
    return (
        model._meta.app_label == TOMBSTONE_APP_LABEL
        and model._meta.model_name == TOMBSTONE_MODEL_NAME
    )


class TombstoneRouter:
    def db_for_read(self, model, **hints):
        if is_tombstone_model(model):
            return TOMBSTONE_ALIAS
        return None

    def db_for_write(self, model, **hints):
        return self.db_for_read(model, **hints)

    def allow_relation(self, obj1, obj2, **hints):
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if model_name is not None:
            holds_tombstone = app_label == TOMBSTONE_APP_LABEL and model_name == TOMBSTONE_MODEL_NAME
            return holds_tombstone == (db == TOMBSTONE_ALIAS)
        if hints.get("tombstone_copy"):
            return db == TOMBSTONE_ALIAS
        if db == TOMBSTONE_ALIAS:
            return False
        return None
