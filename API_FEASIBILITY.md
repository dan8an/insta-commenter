> Historical API research: the active application has pivoted to local browser publishing. See README.md for the current workflow. The API conclusions below do not describe browser-mode confirmation or access.

# Instagram API feasibility

Researched 2026-11-13. Selected Instagram API with Instagram Login, explicit Graph version `v27.0`, host `graph.instagram.com`.

## Decision

**Top-level creation is documented:** `POST /{ig-media-id}/comments`, with `message`, returns an `id`. Implement this only after discovering the target in the connected professional account's media. Do not confuse the media node's unsupported Creating operation with its supported comments edge. No live publishing has been verified in this repository.

Supported application targets: owned feed images, carousel parent objects, videos and Reels with `/p/` or `/reel/` permalinks. Live video comments are explicitly unsupported. Stories, ads, carousel children, tagged and external media are outside this application's scope. Provider permissions and disabled comments can still prevent an otherwise resolved operation.

Resolve by paging `/{user-id}/media`, requesting id, permalink, media_type, and matching normalized permalinks. Shortcodes are never Graph IDs. Cursor pagination stays on a fixed official host; never follow user URLs or provider pagination URLs. An unmatched URL means inaccessible to this connection, not proof that it does not exist or is private.

Requirements: Business or Creator account, Instagram User access token, `instagram_business_basic` and `instagram_business_manage_comments`. Standard Access is for owned/managed accounts added in the app dashboard; serving other customers requires Advanced Access/App Review. Instagram Login does not require the Facebook Login Page-based flow.

Replies use `POST /{ig-comment-id}/replies`; the application provides an explicit reply option and verifies the parent through the resolved media's comments edge. It never converts a comment into a reply. Provider creation must return a nonempty ID before success is recorded. Network failures after a write are indeterminate and never automatically retried.

Text policy: 2,200 Unicode code points maximum as a conservative application limit. The retrieved comments reference does not specify a numeric text limit; do not present this as a newly verified provider guarantee. Provider validation remains authoritative.

## Official sources

- [Comments edge](https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/ig-media/comments): explicit creation, permissions/hosts, no live video, comment pagination.
- [Media reference](https://developers.facebook.com/docs/instagram-platform/reference/instagram-media/v21.0/): current rendered reference identifies v27.0; media types and permalink limitations.
- [Business Login](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login/business-login): OAuth, scopes, server exchange, 60-day tokens and access levels.
- [Replies reference](https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-comment/replies/).
- [Meta-maintained Postman collection](https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api): professional account integration.

Some old `/docs/` moderation URLs could not be fetched; the current `/documentation/` comments edge was readable. Do not assume all future app configurations expose Instagram Login: verify the available product in your Meta dashboard before deployment. This implementation targets that documented login method, not Unified Login.

## Verification gate

Automated provider tests use mocked HTTP responses; demo comments are simulated. Real OAuth, permissions and a visible comment/reply must pass the manual test in README before claiming live integration complete.
