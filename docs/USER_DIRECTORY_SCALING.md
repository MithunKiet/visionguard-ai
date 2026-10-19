# Bounded user administration

The user directory previously returned every visible user and loaded roles with one extra SELECT per user. A local PostgreSQL comparison with 100 user rows measured **102 SELECTs before the change and 4 afterward**. The comparison inserted disposable data in a transaction and rolled it back. This measures query count, not API latency or factory camera capacity.

## API contract

`GET /api/v1/users` retains the `data` array and now includes the standard `meta` pagination object:

```json
{
  "success": true,
  "data": [],
  "meta": {"page": 1, "page_size": 20, "total": 0, "total_pages": 1},
  "error": null
}
```

`page` defaults to 1 and accepts 1–1,000,000. `page_size` defaults to 20 and accepts 1–100. Invalid bounds return HTTP 422. A page past the end returns an empty array with the same scoped total. Consumers that previously assumed an unbounded response must now follow `meta.total_pages`; the application Users page has been updated in the same release.

Both the count and returned rows apply the same enterprise, soft-deletion and factory-visibility predicates. A factory manager cannot infer another factory's user count from pagination metadata. An empty scope returns zero rows and zero total. Existing managing-role requirements remain enforced on the server; the browser also prevents unauthorized direct-navigation queries.

Ordering is by display name and then internal ID as a unique tie breaker. Internal IDs and password hashes are not returned. The role query loads only the current page's public user IDs and retains all roles, including a stable alphabetical role order. Users with no roles or no factory still serialize correctly. The existing user detail/invite/update paths use the same role mapping.

The count and page are separate statements under the existing transaction isolation. Concurrent account changes can move offset-based pages or change their totals; this is not a frozen directory export. Deep offsets and exact counts still require representative database measurement at much larger account volumes. No migration or new database index is introduced.

## Browser behavior

The Users page requests 20 rows at a time and uses the server total. Invite/edit/deactivation invalidates all cached user pages. After deleting the last row on a final page, it returns to the preceding valid page. Failed requests display an error and retry action rather than an empty-directory claim. Deactivation refreshes the list after either success or an uncertain failure, and exposes a manual refresh action.

## Verification

PostgreSQL regressions check default limits, traversal across duplicate names, role completeness, scoped totals, tenant/factory isolation, empty scope, beyond-end pages, invalid bounds and invite/update/deactivation compatibility without sending email. Query-count coverage compares one-row and 100-row pages and requires four SELECTs for both: tenant lookup, scoped count, bounded rows and one batch role query. Existing authorization regressions run alongside them.

Browser regressions cover a second page, last-page deletion, load failure/retry and viewer direct-navigation denial. These use mocked HTTP responses. Real PostgreSQL cases run in the integration CI job; the normal frontend job runs the browser suite. Point-in-time local validation and remaining deployment gates are recorded in [MULTI_FACTORY_REMEDIATION.md](MULTI_FACTORY_REMEDIATION.md).
