"""Registration: the same checks doctor and validate run, but in-process.

If this passes and `hermes plugins doctor` still complains, the difference is
the harness, not us.
"""

from __future__ import annotations

import inspect

import yaml

from dossier import register, schemas

from conftest import ROOT

VALID_HOOKS = {"pre_llm_call"}


class RecordingCtx:
    def __init__(self):
        self.tools = {}
        self.hooks = {}
        self.commands = {}
        self.skills = {}
        self.blueprints = {}

    def register_tool(self, *, name, toolset, schema, handler, **kwargs):
        self.tools[name] = {"toolset": toolset, "schema": schema, "handler": handler}

    def register_hook(self, name, callback, **kwargs):
        self.hooks.setdefault(name, []).append(callback)

    def register_command(self, name, handler=None, description="", args_hint="", **kwargs):
        self.commands[name] = handler

    def register_skill(self, name, path):
        self.skills[name] = path

    def register_automation_blueprint(self, key, **kwargs):
        self.blueprints[key] = kwargs

    def get_config(self, key, default=None):
        return default

    def has_capability(self, _name):
        return False


def _manifest() -> dict:
    return yaml.safe_load((ROOT / "plugin.yaml").read_text(encoding="utf-8"))


def test_register_adds_exactly_the_declared_tools():
    ctx = RecordingCtx()
    register(ctx)
    declared = set(_manifest()["provides_tools"])
    assert set(ctx.tools) == declared
    assert set(ctx.tools) == {s["name"] for s in schemas.ALL}


def test_every_declared_hook_is_registered_and_known():
    ctx = RecordingCtx()
    register(ctx)
    declared = set(_manifest()["provides_hooks"])
    assert set(ctx.hooks) == declared
    assert declared <= VALID_HOOKS


def test_every_hook_accepts_kwargs():
    ctx = RecordingCtx()
    register(ctx)
    for callbacks in ctx.hooks.values():
        for callback in callbacks:
            params = inspect.signature(callback).parameters
            assert any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()), callback


def test_every_tool_handler_accepts_kwargs():
    ctx = RecordingCtx()
    register(ctx)
    for entry in ctx.tools.values():
        params = inspect.signature(entry["handler"]).parameters
        assert any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())


def test_the_slash_command_is_registered():
    ctx = RecordingCtx()
    register(ctx)
    assert "dossier" in ctx.commands


def test_deleting_a_dossier_is_not_a_tool():
    """An irreversible delete gated only by a model-set flag is not gated.

    The reviewer asked for it to stay on `/dossier forget` and the Desktop
    button, so a person is the caller. This fails if it is ever re-registered.
    """
    ctx = RecordingCtx()
    register(ctx)
    assert "dossier_forget" not in ctx.tools


def test_a_scheduled_refresh_blueprint_is_offered():
    ctx = RecordingCtx()
    register(ctx)
    assert "refresh" in ctx.blueprints
    blueprint = ctx.blueprints["refresh"]
    assert "{entity}" in blueprint["prompt_template"]
    assert blueprint["schedule_template"].startswith("{minute} {hour}")


def test_the_watch_tool_is_registered():
    ctx = RecordingCtx()
    register(ctx)
    assert "dossier_watch" in ctx.tools


def test_register_touches_no_database(tmp_path, monkeypatch):
    """The capability probe imports and registers with sockets blocked."""
    import dossier.db as db

    def explode(*args, **kwargs):
        raise AssertionError("register() must not open the database")

    monkeypatch.setattr(db, "connect", explode)
    register(RecordingCtx())
