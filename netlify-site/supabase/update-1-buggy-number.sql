-- ============================================================================
-- Update 1: buggy pass number + term, entered by the admin on the student form.
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run more than once. (Already included in schema.sql for new projects.)
-- ============================================================================

alter table public.students add column if not exists buggy_pass_no text
  check (char_length(buggy_pass_no) <= 20);
alter table public.students add column if not exists pass_term text
  check (char_length(pass_term) <= 60);

-- Each buggy pass number can be given to only one student.
create unique index if not exists students_buggy_pass_no_unique
  on public.students (lower(buggy_pass_no)) where buggy_pass_no is not null;
