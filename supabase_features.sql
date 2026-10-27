-- TriggerMc additive feature schema.
-- Run in Supabase SQL Editor for the ALPHA project before enabling persistent tools.
-- Keep ALPHA_SERVICE_KEY only in Wispbyte private environment variables.
create extension if not exists pgcrypto;

create table if not exists public.authorized_admins (
  id bigint generated always as identity primary key,
  guild_id text not null,
  user_id text not null,
  granted_by text not null,
  created_at timestamptz not null default now(),
  unique (guild_id, user_id)
);

create table if not exists public.giveaways (
  id uuid primary key default gen_random_uuid(),
  guild_id text not null, channel_id text not null, message_id text not null,
  prize text not null, winner_count integer not null default 1 check (winner_count between 1 and 20),
  ends_at timestamptz not null, is_ended boolean not null default false,
  created_by text not null, created_at timestamptz not null default now(), ended_at timestamptz
);
create table if not exists public.giveaway_entries (
  id bigint generated always as identity primary key,
  giveaway_id uuid not null references public.giveaways(id) on delete cascade,
  user_id text not null, created_at timestamptz not null default now(),
  unique (giveaway_id, user_id)
);
create table if not exists public.support_tickets (
  id uuid primary key default gen_random_uuid(),
  guild_id text not null, opener_id text not null, channel_id text not null unique,
  status text not null default 'open' check (status in ('open', 'closed')),
  created_at timestamptz not null default now(), closed_at timestamptz
);
create table if not exists public.tournaments (
  id uuid primary key default gen_random_uuid(),
  guild_id text not null, channel_id text not null, message_id text not null,
  name text not null, gamemode text not null,
  capacity integer not null default 64 check (capacity between 2 and 256),
  status text not null default 'open' check (status in ('open', 'closed')),
  created_by text not null, created_at timestamptz not null default now(), closed_at timestamptz
);
create table if not exists public.tournament_entries (
  id bigint generated always as identity primary key,
  tournament_id uuid not null references public.tournaments(id) on delete cascade,
  user_id text not null, created_at timestamptz not null default now(),
  unique (tournament_id, user_id)
);

alter table public.authorized_admins enable row level security;
alter table public.giveaways enable row level security;
alter table public.giveaway_entries enable row level security;
alter table public.support_tickets enable row level security;
alter table public.tournaments enable row level security;
alter table public.tournament_entries enable row level security;

revoke all on public.authorized_admins, public.giveaways, public.giveaway_entries, public.support_tickets,
  public.tournaments, public.tournament_entries from anon, authenticated;
grant all on public.authorized_admins, public.giveaways, public.giveaway_entries, public.support_tickets,
  public.tournaments, public.tournament_entries to service_role;
grant usage, select on all sequences in schema public to service_role;

create index if not exists idx_authorized_admins_guild_user on public.authorized_admins (guild_id, user_id);
create index if not exists idx_giveaways_guild_active on public.giveaways (guild_id, is_ended);
create index if not exists idx_giveaway_entries_giveaway on public.giveaway_entries (giveaway_id);
create index if not exists idx_support_tickets_channel_status on public.support_tickets (channel_id, status);
create index if not exists idx_tournaments_guild_status on public.tournaments (guild_id, status);
create index if not exists idx_tournament_entries_tournament on public.tournament_entries (tournament_id);
