-- A decision or an approval the gateway refused, since its sign-in didn't check out, no longer
-- stands in the way of its person deciding or approving again, with a new sign-in, as a5s tells
-- them they may (round 12, B6). One the gateway couldn't check just now, since the identity
-- provider couldn't be reached, is neither sealed nor refused: it waits for the next sweep.
do $$
declare
  found record;
begin
  for found in
    select c.conrelid::regclass as tab, c.conname
    from pg_constraint c
    where c.contype = 'u'
      and ((c.conrelid = 'proposal_decisions'::regclass
            and pg_get_constraintdef(c.oid) = 'UNIQUE (digest, person)')
        or (c.conrelid = 'settings_approvals'::regclass
            and pg_get_constraintdef(c.oid) = 'UNIQUE (scenario, digest, person)'))
  loop
    execute format('alter table %s drop constraint %I', found.tab, found.conname);
  end loop;
end $$;

create unique index if not exists proposal_decisions_once
  on proposal_decisions (digest, person) where refused is null;
create unique index if not exists settings_approvals_once
  on settings_approvals (scenario, digest, person) where refused is null;
