# Onboarding Gate — Design (DRAFT, not built, not pushed)

Cayden's ask (2026-11-15): a starting channel, like an initiation — a new
member fills out the profile there, and once it's done they get access to
the rest of the server.

Status: DESIGN ONLY. Nothing coded, nothing committed, nothing deployed.
Build only after Cayden approves this design.

## How it works (the short version)

1. Someone joins the GGA server. They can see exactly ONE channel:
   #start-here. Everything else is hidden from them.
2. In #start-here, pinned instructions + the welcome DM tell them to run
   /profile and fill out the questionnaire.
3. The moment they save a complete profile, the bot gives them a role
   (proposed name: **Verified**). That role is what unlocks every other
   channel.
4. From then on they see the whole server like a normal member.

## What the bot does (code changes)

- **Grant on save.** The /profile save handler grants the Verified role
  right after a complete profile is stored. Granting is idempotent — if
  they already have the role, nothing happens. Re-saving / updating a
  profile never removes it.
- **Grant on rejoin.** On member join, if the person already has a saved
  profile (left and came back), grant the role immediately — no form
  needed a second time.
- **Welcome DM update.** The join DM already points at /profile. Add one
  line: completing it unlocks the rest of the server.
- **Backfill command.** New admin-only `/sync-roles`: grants Verified to
  everyone who already has a complete profile. This is the fix if the bot
  was offline when someone saved, or if a grant fails for any reason.
  (Matches the standing rule: every feature gets its correction path.)
- **No channel-permission code.** The bot does NOT create channels or
  rewrite permissions on the server. See below.

## What Cayden / an admin does in Discord (one-time setup, by hand)

- Create the #start-here channel (bot can also do this later if asked,
  but by hand is safer for a first version).
- Set channel permissions so @everyone can see ONLY #start-here, and
  every other channel/category requires the Verified role.
- Create the Verified role.
- Move the bot's own role ABOVE Verified in the role list — Discord won't
  let a bot hand out a role that sits above its own. (Required. If this
  isn't done, grants fail silently.)
- Give the bot the Manage Roles permission if it doesn't already have it.

Why by hand: the server already has categories, voice channels, and
existing role overwrites. A bot rewriting every channel's permissions in
one go can lock the wrong people out with no easy undo. The bot only
hands out the role; the lockdown is a one-time manual setup with exact
steps written out at build time.

## What counts as "filled it out"

A saved profile with all four required answers: timezone, available
playing time (days + a time window), handicap, preferred tour. Golf+
username is optional and does NOT block the gate.

## Decisions Cayden still needs to make

1. **Existing members — grandfather, or make everyone do it?**
   RECOMMENDATION: grandfather. When the gate goes live, give Verified to
   everyone already in the server (one `/sync-roles` run, or hand it out
   by hand). Otherwise all ~68 current members lose the server until
   they fill out a form — including anyone with DMs closed, who wouldn't
   even know why they lost access.
2. **Role name.** Proposed: Verified. Alternatives: GGA Member, Member.
3. **Channel name.** Proposed: #start-here. (Any name works.)
4. **Profile deleted later?** If an admin deletes someone's profile,
   they KEEP the role (simplest; admin can remove the role by hand if
   needed). Alternative: deleting a profile also strips the role.

## What it deliberately does NOT do

- No forcing: a member who never fills out the form just stays in
  #start-here. They are never kicked.
- No DMs as the only path: if their DMs are closed they still see
  #start-here and its pinned instructions.
- No retroactive lockouts after launch: once someone has Verified, the
  bot never takes it away on its own.

## Rollout order (when approved)

1. Build + test locally (same 51-test suite pattern, plus new tests for
   grant-on-save, grant-on-rejoin, /sync-roles).
2. Cayden does the Discord-side setup (role + channel + permissions).
3. Push to GitHub, deploy to the VM (same SSH pull + install flow as the
   +7 fix — install.sh now restarts the service).
4. Run /sync-roles once to grandfather existing members (if that's the
   call in decision 1).
5. Test with a fresh alt / test account joining: sees only #start-here,
   fills out /profile, gets the role, sees the server.
