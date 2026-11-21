"""Expandable list for the crew/admin roster commands.

Shows the first COLLAPSED_LIMIT entries with a "Show more" button;
tapping it expands the same message to show every entry, and the
button becomes "Show less" to collapse back. No paging — the list
just grows in place.

The expanded list is capped at what fits in one embed description
(Discord caps those at 4096 characters); if the full list is longer
than that, the expanded view shows as many whole lines as fit and
says so in the footer. The button only works for the person who ran
the command, and only until the bot restarts — re-running the
command restores it.
"""
import discord

COLLAPSED_LIMIT = 20
MAX_DESCRIPTION = 4000  # Discord embed descriptions cap at 4096


class ExpandableListView(discord.ui.View):
    """One toggle button that grows or shrinks a roster embed."""

    def __init__(
        self,
        *,
        title: str,
        lines: list[str],
        invoker_id: int,
        colour: discord.Colour,
        collapsed_footer: str,
        expanded_footer: str,
    ):
        super().__init__(timeout=None)
        self.title = title
        self.lines = lines
        self.invoker_id = invoker_id
        self.colour = colour
        self.collapsed_footer = collapsed_footer
        self.expanded_footer = expanded_footer
        self.expanded = False
        self._refresh_button()

    @property
    def has_expand(self) -> bool:
        """True when there are more entries than fit in the collapsed list."""
        return len(self.lines) > COLLAPSED_LIMIT

    def _shown_lines(self) -> list[str]:
        if not self.expanded:
            return self.lines[:COLLAPSED_LIMIT]
        shown: list[str] = []
        total = 0
        for line in self.lines:
            add = len(line) + (1 if shown else 0)
            if total + add > MAX_DESCRIPTION:
                break
            shown.append(line)
            total += add
        return shown

    def _refresh_button(self) -> None:
        hidden = len(self.lines) - COLLAPSED_LIMIT
        self.toggle.label = (
            "Show less"
            if self.expanded
            else f"Show more ({hidden} more)"
        )

    def build_embed(self) -> discord.Embed:
        shown = self._shown_lines()
        embed = discord.Embed(
            title=self.title,
            description="\n".join(shown),
            colour=self.colour,
        )
        if self.expanded:
            if len(shown) == len(self.lines):
                embed.set_footer(text=self.expanded_footer)
            else:
                embed.set_footer(
                    text=f"Showing {len(shown)} of {len(self.lines)} — "
                    "the rest won't fit in one message."
                )
        elif self.has_expand:
            embed.set_footer(text=self.collapsed_footer)
        return embed

    async def interaction_check(
        self, interaction: discord.Interaction
    ) -> bool:
        if interaction.user.id != self.invoker_id:
            await interaction.response.send_message(
                "Only the person who ran the command can expand this list.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Show more", style=discord.ButtonStyle.secondary)
    async def toggle(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.expanded = not self.expanded
        self._refresh_button()
        await interaction.response.edit_message(
            embed=self.build_embed(), view=self
        )
