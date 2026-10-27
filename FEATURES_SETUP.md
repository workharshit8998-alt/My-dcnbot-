# TriggerMc competitive features setup

These changes are additive. The existing `/results` command and tier-role assignment code are unchanged.

## Features
- `/compare player_one player_two` compares tiers from the existing ALPHA-independent BETA `players` table.
- `/support_setup` posts a support panel. Users open private tickets; the opener or support staff can close them.
- `/giveaway_create` creates a persistent giveaway; `/giveaway_end` manually draws winners.
- `/tournament_create`, `/tournament_list`, and `/tournament_close` manage manual tournament signups.

## One-time database setup
1. Open the Supabase project used by `ALPHA_URL`.
2. Open SQL Editor and run the full `supabase_features.sql` file.
3. These new tables have RLS enabled and no access for public `anon` or `authenticated` roles.

## Private bot key required for persistent features
1. In Supabase, copy the ALPHA project's server-side secret key (or legacy service_role key).
2. In Wispbyte, add it as environment variable `ALPHA_SERVICE_KEY`.
3. Never commit this key to GitHub or paste it into chat. It must exist only in the private bot runtime.
4. Restart the bot after adding the variable.

The existing `ALPHA_KEY` and `BETA_KEY` variables are not changed. The new service key is optional at process startup, so missing configuration does not prevent existing commands from starting; persistent support, giveaway, and tournament commands will ask for setup.

## Optional ticket settings
- `SUPPORT_ROLE_ID`: Discord role ID allowed to see and close support tickets.
- `SUPPORT_CATEGORY_ID`: category ID under which new support channels are created.

If these are omitted, tickets are created without a staff role override and in the default channel list. Configure the role for a private staff workflow.

## First test
1. Run `!sync` as a server administrator to synchronize slash commands.
2. Try `/compare` with two usernames already present in the BETA `players` table.
3. In a test channel, run `/support_setup`, `/giveaway_create`, and `/tournament_create`.
4. End tests manually with `/giveaway_end` and `/tournament_close`.

Do not consider the live bot updated until the PR is merged, Wispbyte pulls the new files, the SQL has been applied, the private environment variable is set, and the commands are tested in Discord.
