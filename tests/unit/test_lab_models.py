# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""The lab's model allowlist (lab/models.yaml): local and hosted models, and who may use them."""

from pathlib import Path

import pytest

from exocortex.lab import llm_gateway as gw

MODELS = Path(__file__).resolve().parents[2] / "lab" / "models.yaml"


def test_a_model_outside_the_list_is_refused():
    models = gw.load_models(MODELS)
    with pytest.raises(gw.ModelNotAllowed, match="not in lab/models.yaml"):
        gw.authorize(models, "gpt-9-embed", "public", "local-vs-cloud-embeddings")


@pytest.mark.parametrize("data_class", ["private", "client", "internal", ""])
def test_a_hosted_model_with_data_that_is_not_public_is_refused(data_class):
    models = gw.load_models(MODELS)
    with pytest.raises(gw.ModelNotAllowed, match="public data only"):
        gw.authorize(models, "text-embedding-3-large", data_class, "local-vs-cloud-embeddings")


def test_a_hosted_model_serves_only_its_experiment():
    models = gw.load_models(MODELS)
    assert gw.authorize(models, "text-embedding-3-large", "public", "local-vs-cloud-embeddings")["provider"] == "openai"
    with pytest.raises(gw.ModelNotAllowed, match="may be used only in local-vs-cloud-embeddings"):
        gw.authorize(models, "text-embedding-3-large", "public", "graph-vs-search")
    with pytest.raises(gw.ModelNotAllowed):
        gw.authorize(models, "text-embedding-3-large", "public")


def test_local_models_need_no_experiment():
    models = gw.load_models(MODELS)
    assert gw.authorize(models, "bge-m3", "public")["id"] == "bge-m3"


def test_the_gateway_serves_local_models_only():
    models = gw.load_models(MODELS)
    local = gw.local_models(models)
    assert "text-embedding-3-large" in models and "text-embedding-3-large" not in local
    assert {"bge-m3", "qwen3.6-35b-a3b"} <= local
    status, _, _ = gw.Gateway("http://127.0.0.1:9", local).handle(
        "POST", "/v1/embeddings", b'{"model": "text-embedding-3-large", "input": ["x"]}')
    assert status == 403


@pytest.mark.parametrize("extra, message", [
    ("    data_class: public\n", "missing experiments"),
    ("    experiments: [x]\n", "missing data_class"),
    ("    data_class: private\n    experiments: [x]\n", "needs data_class: public"),
])
def test_a_hosted_entry_without_its_limits_does_not_load(tmp_path, extra, message):
    path = tmp_path / "models.yaml"
    path.write_text("models:\n  - id: m\n    family: f\n    provider: vendor\n    weights: w\n    license: l\n"
                    "    basis: b\n    added_by: agent\n    reason: r\n" + extra, encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        gw.load_models(path)
