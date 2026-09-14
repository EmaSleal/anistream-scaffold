-- Deletes the 8 series rows (and their episodes) confirmed to hold wrong
-- data from the canonical-id collision bug, so a fresh /ingest can rebuild
-- them correctly. Verified against live prod state on 2026-09-13.
--
-- Run the SELECT first to confirm each id still has the mal_id we expect
-- before deleting anything — if a row's mal_id doesn't match, stop and
-- investigate rather than deleting.

-- 1) Verify before deleting
select id, mal_id, title
from series
where id in (
  'tensei-shitara-slime-datta-ken-3rd-season',   -- expect mal_id 59493
  'tensei-shitara-slime-datta-ken-4th-season',   -- expect mal_id 63129
  'kingdom-6th-season',                          -- expect mal_id 63185
  'is-it-wrong-to-try-to-pick-up-girls-in-a-dungeon-ii-is-it-wrong-to-go-searching-for-herbs-on-a-deserted-island', -- expect mal_id 40453
  'is-it-wrong-to-try-to-pick-up-girls-in-a-dungeon-arrow-of-the-orion', -- expect mal_id 37348
  'is-it-wrong-to-try-to-pick-up-girls-in-a-dungeon-iv-play-back', -- expect mal_id 52357
  'danmachi-v',                                  -- expect mal_id 53111
  'mushoku-tensei-ii-isekai-ittara-honki-dasu'   -- expect mal_id 55888
);

-- 2) Delete episodes first (avoids orphaned rows if anything fails midway)
delete from episodes
where series_id in (
  'tensei-shitara-slime-datta-ken-3rd-season',
  'tensei-shitara-slime-datta-ken-4th-season',
  'kingdom-6th-season',
  'is-it-wrong-to-try-to-pick-up-girls-in-a-dungeon-ii-is-it-wrong-to-go-searching-for-herbs-on-a-deserted-island',
  'is-it-wrong-to-try-to-pick-up-girls-in-a-dungeon-arrow-of-the-orion',
  'is-it-wrong-to-try-to-pick-up-girls-in-a-dungeon-iv-play-back',
  'danmachi-v',
  'mushoku-tensei-ii-isekai-ittara-honki-dasu'
);

-- 3) Then delete the series rows themselves
delete from series
where id in (
  'tensei-shitara-slime-datta-ken-3rd-season',
  'tensei-shitara-slime-datta-ken-4th-season',
  'kingdom-6th-season',
  'is-it-wrong-to-try-to-pick-up-girls-in-a-dungeon-ii-is-it-wrong-to-go-searching-for-herbs-on-a-deserted-island',
  'is-it-wrong-to-try-to-pick-up-girls-in-a-dungeon-arrow-of-the-orion',
  'is-it-wrong-to-try-to-pick-up-girls-in-a-dungeon-iv-play-back',
  'danmachi-v',
  'mushoku-tensei-ii-isekai-ittara-honki-dasu'
);
