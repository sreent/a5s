-- a5s's pages and notes are in English alone, so nobody chooses a language for them any more:
-- the choices people made go, as a5s keeps nothing it no longer uses. Agents still answer each
-- person in the language the directory gives them (core/languages.py).
delete from preferences where name = 'language';
