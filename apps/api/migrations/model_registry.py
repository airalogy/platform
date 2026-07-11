from importlib import import_module

MODEL_MODULES = [
    "app.models.account_security",
    "app.models.account_token",
    "app.models.airalogy_file",
    "app.models.answer",
    "app.models.attachment",
    "app.models.chat",
    "app.models.embedding",
    "app.models.group",
    "app.models.lab",
    "app.models.lab_force_delete_job",
    "app.models.oauth",
    "app.models.pinned_item",
    "app.models.project",
    "app.models.project_group",
    "app.models.protocol",
    "app.models.protocol_folder",
    "app.models.protocol_version",
    "app.models.question",
    "app.models.record",
    "app.models.star",
    "app.models.upvote",
    "app.models.user",
    "app.models.user_alias",
    "app.models.workflow",
]


def import_models() -> None:
    for module in MODEL_MODULES:
        import_module(module)
