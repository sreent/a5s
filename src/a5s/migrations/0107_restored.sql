-- Whether a5s restored after a backup a deployment's settings name (`a5s restore --id`, the
-- chart's restore.id), found by its entry in the ledger at each install or upgrade, by an index
-- of its own rather than every entry (round 15, D1)
create index if not exists ledger_restores on ledger (seq) where kind = 'restore';
