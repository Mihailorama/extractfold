from __future__ import annotations

import json

import pytest

from extractfold.discovery import classify_document, propose_schema, shared_context


@pytest.mark.asyncio
async def test_propose_schema_relational_cleans_the_answer() -> None:
    answer = {"tables": [
        {"name": "acts", "schema": {"properties": {"id": {"type": "string"},
                                                   "total": {"type": ["number", "null"]}}},
         "primary_key": "id", "foreign_keys": []},
        {"name": "lines", "schema": {"properties": {"act": {"type": "str"},
                                                    "amount": {"type": "number"}}},
         "primary_key": "missing",
         "foreign_keys": [{"field": "act", "table": "acts", "target_field": "id"},
                          {"field": "act", "table": "ghost", "target_field": "id"}]},
        {"name": "empty", "schema": {"properties": {}}},
    ]}
    prompts: list[str] = []

    def llm(prompt: str) -> str:
        prompts.append(prompt)
        return json.dumps(answer)

    result = await propose_schema(llm=llm, samples=["Act 1 total 10"], attributes=["total"],
                                  relational=True)

    assert "linked tables" in prompts[0] and "Act 1 total 10" in prompts[0]
    acts, lines = result["tables"]
    assert acts["schema"]["properties"]["total"]["type"] == ["number", "null"]
    assert lines["schema"]["properties"]["act"]["type"] == "string"
    assert lines["primary_key"] is None
    assert lines["foreign_keys"] == [{"field": "act", "table": "acts", "target_field": "id"}]

    single = await propose_schema(llm=llm, attributes=["total"])
    assert [t["name"] for t in single["tables"]] == ["acts"]
    with pytest.raises(ValueError):
        await propose_schema(llm=llm)


@pytest.mark.asyncio
async def test_classify_document_only_returns_known_profiles() -> None:
    profiles = [{"id": "invoice", "description": "Invoice"}, {"id": "act", "description": "Act"}]

    async def known(prompt: str) -> str:
        return '{"document_type": "invoice", "profile": "invoice", "confidence": 1.4}'

    async def unknown(prompt: str) -> str:
        return '{"document_type": "letter", "profile": "letter", "confidence": 0.9}'

    assert (await classify_document("Invoice 7", profiles, llm=known)) == {
        "document_type": "invoice", "profile": "invoice", "confidence": 1.0, "rationale": ""}
    other = await classify_document("Dear", profiles, llm=unknown)
    assert other["profile"] is None and other["confidence"] == 0.5


@pytest.mark.asyncio
async def test_shared_context_keeps_sourced_defaults() -> None:
    def llm(prompt: str) -> str:
        assert "File letter.txt:\nContract C-1" in prompt
        return json.dumps({"defaults": {"contract": "C-1", "site": "", "ghost": "x",
                                        "client": "Acme"},
                           "sources": {"contract": "letter.txt", "client": "nowhere.txt"}})

    result = await shared_context({"letter.txt": "Contract C-1", "act.txt": "Act"},
                                  ["contract", "site", "client"], llm=llm)

    assert result["defaults"] == {"contract": "C-1"}
    assert result["sources"] == {"contract": "letter.txt"}
    assert "- contract: C-1" in result["context"]
