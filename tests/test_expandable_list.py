"""Expandable roster list: first 20 shown, Show more grows it in place."""
import asyncio
from types import SimpleNamespace

import discord

from src.expandable_list import (
    COLLAPSED_LIMIT,
    MAX_DESCRIPTION,
    ExpandableListView,
)


def _view(n, *, invoker_id=123):
    lines = [f"Player {i:02d} — Golf+ player{i} | Evenings | HCP 8" for i in range(1, n + 1)]
    return ExpandableListView(
        title=f"Roster — {n} registered",
        lines=lines,
        invoker_id=invoker_id,
        colour=discord.Colour.green(),
        collapsed_footer=f"Showing the first {COLLAPSED_LIMIT} of {n}.",
        expanded_footer=f"Showing all {n}.",
    )


class _FakeButtonResponse:
    def __init__(self):
        self.sent = []
        self.edited = []

    async def send_message(self, content=None, **kwargs):
        self.sent.append((content, kwargs))

    async def edit_message(self, **kwargs):
        self.edited.append(kwargs)


class _FakeButtonInteraction:
    def __init__(self, user_id):
        self.user = SimpleNamespace(id=user_id)
        self.response = _FakeButtonResponse()


def test_collapsed_shows_first_20_with_more_button():
    view = _view(25)
    assert view.has_expand is True
    assert view.toggle.label == "Show more (5 more)"
    embed = view.build_embed()
    assert len(embed.description.splitlines()) == 20
    assert "Player 01" in embed.description
    assert "Player 25" not in embed.description
    assert embed.footer.text == "Showing the first 20 of 25."


def test_show_more_expands_in_place_and_back():
    view = _view(25)
    interaction = _FakeButtonInteraction(user_id=123)

    async def _click():
        await view.children[0].callback(interaction)

    asyncio.run(_click())
    assert len(interaction.response.edited) == 1
    embed = interaction.response.edited[0]["embed"]
    assert len(embed.description.splitlines()) == 25
    assert "Player 25" in embed.description
    assert embed.footer.text == "Showing all 25."
    assert view.toggle.label == "Show less"
    assert interaction.response.edited[0]["view"] is view

    asyncio.run(_click())
    embed = interaction.response.edited[1]["embed"]
    assert len(embed.description.splitlines()) == 20
    assert embed.footer.text == "Showing the first 20 of 25."
    assert view.toggle.label == "Show more (5 more)"


def test_short_list_has_no_expand():
    view = _view(20)
    assert view.has_expand is False
    embed = view.build_embed()
    assert len(embed.description.splitlines()) == 20
    assert embed.footer.text is None


def test_only_invoker_can_expand():
    view = _view(25)
    other = _FakeButtonInteraction(user_id=999)
    assert asyncio.run(view.interaction_check(other)) is False
    assert other.response.sent == [
        (
            "Only the person who ran the command can expand this list.",
            {"ephemeral": True},
        )
    ]
    invoker = _FakeButtonInteraction(user_id=123)
    assert asyncio.run(view.interaction_check(invoker)) is True
    assert invoker.response.sent == []


def test_expanded_list_capped_by_description_limit():
    lines = ["x" * 500 for _ in range(25)]
    view = ExpandableListView(
        title="Roster — 25 registered",
        lines=lines,
        invoker_id=123,
        colour=discord.Colour.green(),
        collapsed_footer="Showing the first 20 of 25.",
        expanded_footer="Showing all 25.",
    )
    view.expanded = True
    embed = view.build_embed()
    shown = embed.description.splitlines()
    # 500 chars a line plus newlines: 7 lines fit in 4000, the 8th would not.
    assert len(shown) == 7
    assert len(embed.description) <= MAX_DESCRIPTION
    assert embed.footer.text == (
        "Showing 7 of 25 — the rest won't fit in one message."
    )
