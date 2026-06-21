-- Migrate species_name.language_code + story.language_code from 2-letter
-- (ISO 639-1) to 3-letter (ISO 639-3) uppercase. Idempotent: re-runs only
-- update rows still on the 2-letter form.

BEGIN;

-- species_name --------------------------------------------------------------
UPDATE species_name SET language_code = 'ENG' WHERE lower(language_code) = 'en';
UPDATE species_name SET language_code = 'SPA' WHERE lower(language_code) = 'es';
UPDATE species_name SET language_code = 'FRA' WHERE lower(language_code) = 'fr';
UPDATE species_name SET language_code = 'POR' WHERE lower(language_code) = 'pt';
UPDATE species_name SET language_code = 'DEU' WHERE lower(language_code) = 'de';
UPDATE species_name SET language_code = 'ITA' WHERE lower(language_code) = 'it';
UPDATE species_name SET language_code = 'RUS' WHERE lower(language_code) = 'ru';
UPDATE species_name SET language_code = 'ARA' WHERE lower(language_code) = 'ar';
UPDATE species_name SET language_code = 'ZHO' WHERE lower(language_code) = 'zh';
UPDATE species_name SET language_code = 'JPN' WHERE lower(language_code) = 'ja';
UPDATE species_name SET language_code = 'KOR' WHERE lower(language_code) = 'ko';
UPDATE species_name SET language_code = 'HIN' WHERE lower(language_code) = 'hi';
UPDATE species_name SET language_code = 'BEN' WHERE lower(language_code) = 'bn';
UPDATE species_name SET language_code = 'URD' WHERE lower(language_code) = 'ur';
UPDATE species_name SET language_code = 'PAN' WHERE lower(language_code) = 'pa';
UPDATE species_name SET language_code = 'TAM' WHERE lower(language_code) = 'ta';
UPDATE species_name SET language_code = 'TUR' WHERE lower(language_code) = 'tr';
UPDATE species_name SET language_code = 'FAS' WHERE lower(language_code) = 'fa';
UPDATE species_name SET language_code = 'HEB' WHERE lower(language_code) = 'he';
UPDATE species_name SET language_code = 'HYE' WHERE lower(language_code) = 'hy';
UPDATE species_name SET language_code = 'KAT' WHERE lower(language_code) = 'ka';
UPDATE species_name SET language_code = 'ELL' WHERE lower(language_code) = 'el';
UPDATE species_name SET language_code = 'POL' WHERE lower(language_code) = 'pl';
UPDATE species_name SET language_code = 'UKR' WHERE lower(language_code) = 'uk';
UPDATE species_name SET language_code = 'NLD' WHERE lower(language_code) = 'nl';
UPDATE species_name SET language_code = 'SWE' WHERE lower(language_code) = 'sv';
UPDATE species_name SET language_code = 'NOR' WHERE lower(language_code) = 'no';
UPDATE species_name SET language_code = 'FIN' WHERE lower(language_code) = 'fi';
UPDATE species_name SET language_code = 'VIE' WHERE lower(language_code) = 'vi';
UPDATE species_name SET language_code = 'THA' WHERE lower(language_code) = 'th';
UPDATE species_name SET language_code = 'IND' WHERE lower(language_code) = 'id';
UPDATE species_name SET language_code = 'FIL' WHERE lower(language_code) = 'tl';
UPDATE species_name SET language_code = 'SWA' WHERE lower(language_code) = 'sw';
UPDATE species_name SET language_code = 'YOR' WHERE lower(language_code) = 'yo';
UPDATE species_name SET language_code = 'IBO' WHERE lower(language_code) = 'ig';
UPDATE species_name SET language_code = 'HAU' WHERE lower(language_code) = 'ha';
UPDATE species_name SET language_code = 'AMH' WHERE lower(language_code) = 'am';
UPDATE species_name SET language_code = 'ZUL' WHERE lower(language_code) = 'zu';
UPDATE species_name SET language_code = 'XHO' WHERE lower(language_code) = 'xh';
UPDATE species_name SET language_code = 'SOM' WHERE lower(language_code) = 'so';
UPDATE species_name SET language_code = 'QUE' WHERE lower(language_code) = 'qu';
UPDATE species_name SET language_code = 'AYM' WHERE lower(language_code) = 'ay';
UPDATE species_name SET language_code = 'GRN' WHERE lower(language_code) = 'gn';
UPDATE species_name SET language_code = 'MRI' WHERE lower(language_code) = 'mi';
UPDATE species_name SET language_code = 'LAT' WHERE lower(language_code) = 'la';
UPDATE species_name SET language_code = 'SAN' WHERE lower(language_code) = 'sa';

-- Anything else still lowercase or 2-letter: uppercase it (best effort).
UPDATE species_name
   SET language_code = upper(language_code)
 WHERE language_code <> upper(language_code);

-- story (mirror the same swaps for story.language_code) -------------------
UPDATE story SET language_code = 'ENG' WHERE lower(language_code) = 'en';
UPDATE story SET language_code = 'SPA' WHERE lower(language_code) = 'es';
UPDATE story SET language_code = 'FRA' WHERE lower(language_code) = 'fr';
UPDATE story SET language_code = 'POR' WHERE lower(language_code) = 'pt';
UPDATE story SET language_code = 'DEU' WHERE lower(language_code) = 'de';
UPDATE story SET language_code = 'HYE' WHERE lower(language_code) = 'hy';
UPDATE story SET language_code = 'HIN' WHERE lower(language_code) = 'hi';
UPDATE story SET language_code = 'PAN' WHERE lower(language_code) = 'pa';
UPDATE story SET language_code = 'SWA' WHERE lower(language_code) = 'sw';
UPDATE story SET language_code = 'JPN' WHERE lower(language_code) = 'ja';
UPDATE story SET language_code = 'ZHO' WHERE lower(language_code) = 'zh';
UPDATE story SET language_code = 'ARA' WHERE lower(language_code) = 'ar';
UPDATE story SET language_code = 'TUR' WHERE lower(language_code) = 'tr';
UPDATE story
   SET language_code = upper(language_code)
 WHERE language_code <> upper(language_code);

COMMIT;

-- Verify
SELECT language_code, count(*) AS rows_with
  FROM species_name
  GROUP BY language_code
  ORDER BY rows_with DESC
  LIMIT 30;
