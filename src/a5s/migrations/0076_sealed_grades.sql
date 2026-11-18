-- Round 13, A2: the channels app records a grade and the sign-in that gave it, and the gateway
-- alone seals it (core/samples.py). The channels app could still write a grade's seal, so it
-- could clear one, and the gateway sealed the grade again, later, to count in another window,
-- such as after a critical error lowered the cap. It no longer writes the seal, and changes
-- nothing of a grade the gateway has sealed.
revoke update (grade_seal) on samples from a5s_channels;

create or replace function a5s_sealed_grades() returns trigger language plpgsql as $$
begin
  if old.grade_seal is not null
     and pg_has_role(current_user, 'a5s_channels', 'MEMBER')
     and not pg_has_role(current_user, 'a5s_gateway', 'MEMBER')
     and (new.grade, new.graded_by, new.graded_at, new.grade_token, new.grade_nonce,
          new.grade_salt, new.grade_issuer, new.grade_subject, new.grade_proof)
         is distinct from
         (old.grade, old.graded_by, old.graded_at, old.grade_token, old.grade_nonce,
          old.grade_salt, old.grade_issuer, old.grade_subject, old.grade_proof) then
    raise exception 'a grade the core has sealed is the core''s: the channels app changes none of it';
  end if;
  return new;
end $$;
alter function a5s_sealed_grades() owner to a5s_owner;
drop trigger if exists a5s_sealed_grades on samples;
create trigger a5s_sealed_grades before update on samples
  for each row execute function a5s_sealed_grades();
