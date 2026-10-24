-- CashGuard Risk - Supabase (PostgreSQL) schema with Row Level Security
-- Paste into the Supabase SQL editor. Permissions are enforced by the DATABASE, not only the app:
--   Owner    : sees and decides everything, edits settings and limits
--   Manager  : sees risk data, decides items up to the business's manager limit, never their own
--   Employee : submits bills/requests, sees only their own submissions, never cash or customer data
--   Audit log: insert-only for everyone (no update, no delete)

create extension if not exists pgcrypto;

-- ------------------------------------------------------------------ businesses and people
create table businesses (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  cash_today numeric(12,2) not null default 0,
  min_reserve numeric(12,2) not null default 2000,
  low_risk_limit numeric(4,3) not null default 0.05,
  high_risk_limit numeric(4,3) not null default 0.20,
  manager_approval_limit numeric(12,2) not null default 300,   -- max per item a manager may decide
  manager_monthly_limit numeric(12,2) not null default 1500,   -- total a manager may approve per month (checked in the app)
  owner_whatsapp text
);

create table profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  business_id uuid not null references businesses(id),
  full_name text not null,
  role text not null check (role in ('owner', 'manager', 'employee'))
);

-- Helper functions used by the security rules
create or replace function my_business() returns uuid
language sql stable security definer set search_path = public as $$
  select business_id from profiles where id = auth.uid()
$$;

create or replace function my_role() returns text
language sql stable security definer set search_path = public as $$
  select role from profiles where id = auth.uid()
$$;

create or replace function manager_limit() returns numeric
language sql stable security definer set search_path = public as $$
  select manager_approval_limit from businesses where id = my_business()
$$;

-- ------------------------------------------------------------------ money data
create table bills (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references businesses(id) default my_business(),
  bill_no text not null,
  supplier text not null,
  amount numeric(12,2) not null check (amount > 0),
  issue_date date,
  due_date date not null,
  status text not null default 'Awaiting review'
    check (status in ('Awaiting review', 'To pay', 'Scheduled', 'On hold', 'Paid')),
  pay_date date,
  category text,
  source text,                       -- Uploaded / WhatsApp / Recurring / Expense request
  repeat text default '',            -- 'monthly' for recurring bills
  file_path text,                    -- Supabase Storage path of the invoice image/PDF
  captured_by uuid not null references profiles(id) default auth.uid(),
  approved_by uuid references profiles(id),
  created_at timestamptz not null default now(),
  unique (business_id, supplier, bill_no)        -- duplicate protection in the database
);

create table sales_invoices (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references businesses(id) default my_business(),
  invoice_no text not null,
  customer text not null,
  amount numeric(12,2) not null,
  issue_date date,
  due_date date not null,
  paid_date date
);

create table daily_sales (
  business_id uuid not null references businesses(id) default my_business(),
  date date not null,
  net_cash numeric(12,2) not null,
  primary key (business_id, date)
);

create table spending_categories (
  business_id uuid not null references businesses(id) default my_business(),
  name text not null,
  max_per_request numeric(12,2) not null,
  monthly_limit numeric(12,2) not null,
  primary key (business_id, name)
);

create table expense_requests (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references businesses(id) default my_business(),
  request_no text not null,
  category text not null,
  item text not null,
  amount numeric(12,2) not null check (amount > 0),
  reason text,
  needed_by date,
  submitted_by uuid not null references profiles(id) default auth.uid(),
  submitted_at timestamptz not null default now(),
  status text not null default 'Pending' check (status in ('Pending', 'Approved', 'Rejected')),
  decision text,
  decision_date date,
  decision_reason text,
  decided_by uuid references profiles(id),
  risk_at_decision numeric(5,4)
);

create table whatsapp_senders (
  business_id uuid not null references businesses(id) default my_business(),
  number text not null,
  name text not null,
  type text not null check (type in ('Supplier', 'Staff')),
  primary key (business_id, number)
);

create table audit_log (
  id bigint generated always as identity primary key,
  business_id uuid not null references businesses(id) default my_business(),
  time timestamptz not null default now(),
  actor uuid references profiles(id) default auth.uid(),
  actor_label text not null,
  action text not null,
  details text
);

-- ------------------------------------------------------------------ turn on Row Level Security
alter table businesses enable row level security;
alter table profiles enable row level security;
alter table bills enable row level security;
alter table sales_invoices enable row level security;
alter table daily_sales enable row level security;
alter table spending_categories enable row level security;
alter table expense_requests enable row level security;
alter table whatsapp_senders enable row level security;
alter table audit_log enable row level security;

-- Businesses: cash and limits visible to owner/manager only; only the owner edits
create policy biz_read on businesses for select using (id = my_business() and my_role() in ('owner', 'manager'));
create policy biz_edit on businesses for update using (id = my_business() and my_role() = 'owner');

-- Profiles: everyone sees colleagues' names in their own business; owner manages roles
create policy prof_read on profiles for select using (business_id = my_business());
create policy prof_owner on profiles for all using (business_id = my_business() and my_role() = 'owner');

-- Bills: anyone may submit (as Awaiting review); employees see only their own
create policy bills_insert on bills for insert
  with check (business_id = my_business() and captured_by = auth.uid() and status = 'Awaiting review');
create policy bills_read on bills for select
  using (business_id = my_business() and (my_role() in ('owner', 'manager') or captured_by = auth.uid()));
create policy bills_owner_decide on bills for update
  using (business_id = my_business() and my_role() = 'owner' and captured_by <> auth.uid());
create policy bills_manager_decide on bills for update
  using (business_id = my_business() and my_role() = 'manager'
         and amount <= manager_limit() and captured_by <> auth.uid());

-- Customer invoices and sales history: owner/manager only
create policy inv_read on sales_invoices for select using (business_id = my_business() and my_role() in ('owner', 'manager'));
create policy inv_owner on sales_invoices for all using (business_id = my_business() and my_role() = 'owner');
create policy sales_read on daily_sales for select using (business_id = my_business() and my_role() in ('owner', 'manager'));
create policy sales_owner on daily_sales for all using (business_id = my_business() and my_role() = 'owner');

-- Spending categories: everyone reads (to see their limits); owner edits
create policy cat_read on spending_categories for select using (business_id = my_business());
create policy cat_owner on spending_categories for all using (business_id = my_business() and my_role() = 'owner');

-- Expense requests: submit your own; employees see their own; separation of duties on decisions
create policy req_insert on expense_requests for insert
  with check (business_id = my_business() and submitted_by = auth.uid() and status = 'Pending');
create policy req_read on expense_requests for select
  using (business_id = my_business() and (my_role() in ('owner', 'manager') or submitted_by = auth.uid()));
create policy req_owner_decide on expense_requests for update
  using (business_id = my_business() and my_role() = 'owner' and submitted_by <> auth.uid());
create policy req_manager_decide on expense_requests for update
  using (business_id = my_business() and my_role() = 'manager'
         and amount <= manager_limit() and submitted_by <> auth.uid());

-- Registered WhatsApp senders: owner only
create policy wa_owner on whatsapp_senders for all using (business_id = my_business() and my_role() = 'owner');

-- Audit log: INSERT-ONLY. No update or delete policy exists, so nobody can change history.
create policy audit_insert on audit_log for insert with check (business_id = my_business() and actor = auth.uid());
create policy audit_read on audit_log for select
  using (business_id = my_business() and (my_role() = 'owner' or actor = auth.uid()));
revoke update, delete on audit_log from authenticated, anon;

-- Invoice files: create a PRIVATE Storage bucket called 'invoices' in the Supabase dashboard,
-- store files under <business_id>/<file>, and add Storage policies so members can upload to
-- their own business folder and only owner/manager can read other people's files.
-- The WhatsApp webhook should use the service-role key on the SERVER only - never in GitHub.
