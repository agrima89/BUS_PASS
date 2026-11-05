-- ============================================================================
-- CU Bus Pass: Supabase schema
-- Run once in Supabase: Dashboard -> SQL Editor -> New query -> paste -> Run.
-- Safe to re-run (uses IF NOT EXISTS / OR REPLACE).
-- ============================================================================

create extension if not exists pgcrypto with schema extensions;

-- ---------- Tables -----------------------------------------------------------

create table if not exists public.pickup_points (
  id         bigint generated always as identity primary key,
  name       text not null check (char_length(name) between 1 and 80),
  active     boolean not null default true,
  created_at timestamptz not null default now()
);
create unique index if not exists pickup_points_name_ci on public.pickup_points (lower(name));

create table if not exists public.students (
  id                bigint generated always as identity primary key,
  roll_number       text not null unique check (char_length(roll_number) between 1 and 40),   -- shown as UID
  full_name         text not null check (char_length(full_name) between 1 and 120),
  program           text not null check (char_length(program) between 1 and 80),           -- Class / Program
  department        text check (char_length(department) <= 80),                            -- Branch / Department
  year_of_study     int  check (year_of_study between 1 and 8),
  email             text check (char_length(email) <= 120),
  phone             text check (char_length(phone) <= 20),
  blood_group       text check (blood_group in ('A+','A-','B+','B-','AB+','AB-','O+','O-')),
  valid_until       date,
  status            text not null default 'active' check (status in ('active','inactive','suspended')),
  guardian_relation text check (guardian_relation in ('S/O','D/O','W/O','C/O')),
  guardian_name     text check (char_length(guardian_name) <= 120),
  pickup_point_id   bigint references public.pickup_points(id) on delete set null,
  emergency_contact text check (char_length(emergency_contact) <= 20),
  address           text check (char_length(address) <= 300),
  photo_path        text,                                                                 -- object in the 'photos' bucket
  buggy_pass_no     text check (char_length(buggy_pass_no) <= 20),                         -- entered by the admin, e.g. 38
  pass_term         text check (char_length(pass_term) <= 60),                             -- e.g. (2026-2027) (06 Months)
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now()
);

create table if not exists public.passes (
  id         bigint generated always as identity primary key,
  student_id bigint not null references public.students(id) on delete cascade,
  pass_code  text not null unique,
  qr_token   text not null unique,
  issued_at  timestamptz not null default now(),
  expires_at date,
  status     text not null default 'valid' check (status in ('valid','revoked','expired')),
  qr_mode    text not null default 'offline' check (qr_mode in ('online','offline'))
);
create unique index if not exists students_buggy_pass_no_unique
  on public.students (lower(buggy_pass_no)) where buggy_pass_no is not null;

-- At most one valid pass per student.
create unique index if not exists passes_one_valid_per_student on public.passes (student_id) where status = 'valid';

create table if not exists public.verifications (
  id         bigint generated always as identity primary key,
  pass_id    bigint references public.passes(id) on delete set null,
  result     text not null,
  method     text not null default 'online',
  checked_at timestamptz not null default now()
);

create table if not exists public.settings (
  key   text primary key,
  value text
);

-- Keep updated_at current.
create or replace function public.touch_updated_at() returns trigger language plpgsql as $$
begin new.updated_at := now(); return new; end $$;
drop trigger if exists students_touch on public.students;
create trigger students_touch before update on public.students
  for each row execute function public.touch_updated_at();

-- ---------- Row-level security: signed-in staff only ------------------------

alter table public.pickup_points enable row level security;
alter table public.students      enable row level security;
alter table public.passes        enable row level security;
alter table public.verifications enable row level security;
alter table public.settings      enable row level security;

do $$
declare t text;
begin
  foreach t in array array['pickup_points','students','passes','verifications','settings'] loop
    execute format('drop policy if exists staff_all on public.%I', t);
    execute format('create policy staff_all on public.%I for all to authenticated using (true) with check (true)', t);
  end loop;
end $$;
-- The anon (public) role gets NO table access. Public checks go through verify_pass() below.

-- ---------- Issue a pass (atomic, unique codes) -----------------------------

create or replace function public.issue_pass(p_student bigint, p_mode text default 'offline')
returns bigint
language plpgsql
security invoker            -- runs with the caller's rights, so RLS still applies
set search_path = public, extensions
as $$
declare
  s        public.students%rowtype;
  v_prefix text;
  v_code   text;
  v_token  text;
  v_id     bigint;
  alphabet constant text := 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';   -- no 0/O/1/I confusion
  i int;
begin
  select * into s from public.students where id = p_student;
  if not found then raise exception 'Student not found'; end if;
  if s.status <> 'active' then raise exception 'Only active students can be issued a pass'; end if;
  if s.valid_until is not null and s.valid_until < current_date then
    raise exception 'The valid-until date is in the past';
  end if;
  if p_mode not in ('online','offline') then p_mode := 'offline'; end if;

  select coalesce(nullif(value, ''), 'CU') into v_prefix from public.settings where key = 'pass_prefix';
  v_prefix := coalesce(v_prefix, 'CU');

  update public.passes set status = 'revoked' where student_id = p_student and status = 'valid';

  for attempt in 1..5 loop
    v_code := '';
    for i in 1..6 loop
      v_code := v_code || substr(alphabet, 1 + (get_byte(gen_random_bytes(1), 0) % 32), 1);
    end loop;
    v_code  := v_prefix || '-' || extract(year from now())::int || '-' || v_code;
    v_token := translate(encode(gen_random_bytes(24), 'base64'), '+/=', '-_');   -- 192-bit, URL-safe
    begin
      insert into public.passes (student_id, pass_code, qr_token, expires_at, qr_mode)
      values (p_student, v_code, v_token, s.valid_until, p_mode)
      returning id into v_id;
      return v_id;
    exception when unique_violation then
      -- practically impossible; try again with fresh random values
    end;
  end loop;
  raise exception 'Could not generate a unique pass code';
end $$;

revoke all on function public.issue_pass(bigint, text) from public, anon;
grant execute on function public.issue_pass(bigint, text) to authenticated;

-- ---------- Public verification (online QR) ---------------------------------
-- Anyone who scans an online QR may call this. It returns ONLY non-private
-- fields and records the check. Guardian, phone and address are never returned.

create or replace function public.verify_pass(p_token text)
returns json
language plpgsql
security definer
set search_path = public
as $$
declare
  r record;
  v_status text;
begin
  if p_token is null or length(p_token) > 64 then
    return json_build_object('status', 'not_found');
  end if;
  select p.id, p.pass_code, p.status, p.expires_at, s.full_name, s.roll_number, s.program,
         s.status as student_status
    into r
    from public.passes p join public.students s on s.id = p.student_id
   where p.qr_token = p_token;

  if not found then
    insert into public.verifications (pass_id, result, method) values (null, 'not_found', 'online');
    return json_build_object('status', 'not_found');
  end if;

  v_status := case
    when r.status = 'revoked' or r.student_status <> 'active' then 'revoked'
    when r.expires_at is not null and r.expires_at < current_date then 'expired'
    else 'valid' end;
  insert into public.verifications (pass_id, result, method) values (r.id, v_status, 'online');

  return json_build_object('status', v_status, 'pass_code', r.pass_code, 'name', r.full_name,
                           'uid', r.roll_number, 'program', r.program, 'valid_until', r.expires_at);
end $$;

revoke all on function public.verify_pass(text) from public;
grant execute on function public.verify_pass(text) to anon, authenticated;

-- ---------- Photo storage (private bucket) ----------------------------------

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('photos', 'photos', false, 5242880, array['image/jpeg'])
on conflict (id) do nothing;

drop policy if exists staff_photos_all on storage.objects;
create policy staff_photos_all on storage.objects for all to authenticated
  using (bucket_id = 'photos') with check (bucket_id = 'photos');

-- Make the API notice schema changes immediately.
notify pgrst, 'reload schema';
