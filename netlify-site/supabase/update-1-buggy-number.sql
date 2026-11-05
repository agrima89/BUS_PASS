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

-- Make the API notice the new columns immediately (fixes "column ... not found in the schema cache").
notify pgrst, 'reload schema';

-- Check: this should list buggy_pass_no and pass_term.
select column_name from information_schema.columns
 where table_schema = 'public' and table_name = 'students' and column_name in ('buggy_pass_no', 'pass_term');
