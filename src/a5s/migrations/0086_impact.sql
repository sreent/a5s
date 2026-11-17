-- What a version of the settings would do differently (core/impact.py) reads the latest tool
-- calls the ledger keeps, newest first: by an index of its own, rather than by every entry
create index if not exists ledger_tools on ledger (seq) where kind = 'tool';
