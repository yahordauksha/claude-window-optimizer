import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

import pytest
from window_optimizer.ping_content import (
    SAFE_PROMPTS,
    allowed_tools,
    pick_prompts,
    prompt_for_key,
)


def test_grant_is_minimal_but_never_empty():
    """[] is read by the API as "unset" and replaced with the account's full default
    tool set — Bash, Write, Edit, SendUserFile and the rest. A routine created with []
    came back granting all of them. Non-empty lists are honoured exactly, so the
    narrowest expressible grant is one harmless tool. Never loosen this to []."""
    assert allowed_tools() == ["TodoWrite"]
    assert allowed_tools() != []


def test_no_prompt_references_external_data():
    """The whole reason this pool exists: an earlier design had resets fetch a GitHub
    repo's issue titles, feeding stranger-authored text to an unattended agent. Nothing
    in the pool may reach outside itself."""
    forbidden = ("http://", "https://", "api.", "fetch", "webfetch", "curl", "github", "read the", "look up")
    for key, entry in SAFE_PROMPTS.items():
        text = entry["prompt"].lower()
        for token in forbidden:
            assert token not in text, f"{key!r} prompt references external data: {token!r}"


def test_every_entry_has_a_title_and_prompt():
    for key, entry in SAFE_PROMPTS.items():
        assert entry["title"].strip(), f"{key} has no title"
        assert entry["prompt"].strip(), f"{key} has no prompt"


def test_prompts_stay_short():
    """These fire four times a day on the cheapest model; a long prompt is wasted spend."""
    for key, entry in SAFE_PROMPTS.items():
        assert len(entry["prompt"]) <= 120, f"{key} prompt is {len(entry['prompt'])} chars"


def test_prompt_for_key_returns_the_entry():
    got = prompt_for_key("water")
    assert got["key"] == "water"
    assert got["title"] == "Water"
    assert "water" in got["prompt"].lower()


def test_prompt_for_key_rejects_unknown():
    with pytest.raises(ValueError):
        prompt_for_key("definitely-not-a-key")


def test_pick_prompts_returns_distinct_entries():
    """Four routines saying the same thing four times a day would be worse than useless."""
    picked = pick_prompts(4, rng=random.Random(0))
    assert len(picked) == 4
    assert len({p["key"] for p in picked}) == 4


def test_pick_prompts_is_reproducible_with_a_seed():
    a = pick_prompts(4, rng=random.Random(42))
    b = pick_prompts(4, rng=random.Random(42))
    assert [p["key"] for p in a] == [p["key"] for p in b]


def test_pick_prompts_actually_varies():
    seen = {tuple(p["key"] for p in pick_prompts(4, rng=random.Random(s))) for s in range(20)}
    assert len(seen) > 1, "picker returned the same set for every seed"


def test_pick_prompts_refuses_more_than_the_pool_holds():
    with pytest.raises(ValueError):
        pick_prompts(len(SAFE_PROMPTS) + 1)
