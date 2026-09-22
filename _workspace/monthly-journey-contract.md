# Monthly Journey implementation contract

Read `docs/specs/active/2026-09-22-monthly-journey.md` §§5–7 as canonical API.
G2 GO after version-bound export / strict immutable private-image fixes.
Kinds: diet | life_event | chat_photo. Images: {key,url}, never image_urls.
All collection responses: {items,total,offset,limit}; month adds month.
Paths: /journey/sources, /journey/places/{kind}/{source_id} PUT,
/journey/month GET, /journey/places/{id} DELETE with expected_version,
/journey/export-preview POST {items:[{place_id,version,image_keys}]}.
No country field in v1. City is encrypted at rest. Dates are YYYY-MM-DD.
Images only canonical owner/source-bound immutable chat/diet private paths.
Monthly source type includes title only private UI; export type never title.
Export preview has month and items:{city,local_date,kind,images:[{key,url}]}[].
Foreground device location only on today confirmed date. Manual city always works.
Main owns docs, native app.json/config/tests, generated API types/maps/integration.
Backend owns backend journey feature/API wiring/migrations/tests only.
Mobile owns journey page/components/services/tests and Chat more navigation only.
No branch switches, commits, production operations, or deploy by delegates.
