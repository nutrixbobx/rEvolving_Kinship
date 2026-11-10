-- Normalize species_name.script to ISO 15924 four-letter codes.
--
-- The script picker stored its own display label ("Gurmukhi (Panjabi)"),
-- while names loaded from a CSV carried the real code ("Guru"), so the
-- same writing system was recorded two different ways and could not be
-- filtered or counted. Languages were already standardized to ISO 639-3
-- by db/iso639_3_migration.sql; this is the sibling fix for scripts.
--
-- Idempotent: rows already holding a code are left alone.

BEGIN;

UPDATE species_name SET script = 'Deva'
 WHERE script ILIKE 'Devanagari%';
UPDATE species_name SET script = 'Guru'
 WHERE script ILIKE 'Gurmukhi%' OR script ILIKE 'Panjabi%'
    OR script ILIKE 'Punjabi%';
UPDATE species_name SET script = 'Cyrl'
 WHERE script ILIKE 'Cyrillic%';
UPDATE species_name SET script = 'Hira'
 WHERE script ILIKE 'Hiragana%';
UPDATE species_name SET script = 'Kana'
 WHERE script ILIKE 'Katakana%';
UPDATE species_name SET script = 'Beng' WHERE script ILIKE 'Bengali%';
UPDATE species_name SET script = 'Taml' WHERE script ILIKE 'Tamil%';
UPDATE species_name SET script = 'Armn' WHERE script ILIKE 'Armenian%';
UPDATE species_name SET script = 'Arab' WHERE script ILIKE 'Arabic%';
UPDATE species_name SET script = 'Hebr' WHERE script ILIKE 'Hebrew%';
UPDATE species_name SET script = 'Grek' WHERE script ILIKE 'Greek%';
UPDATE species_name SET script = 'Latn'
 WHERE script ILIKE 'Latin%' OR script ILIKE 'Roman%';

-- Blank strings are not a script; leave them absent instead.
UPDATE species_name SET script = NULL WHERE trim(coalesce(script,'')) = '';

COMMIT;
