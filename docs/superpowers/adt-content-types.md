# ADT content-type version inventory (pkg/adt) — 406/404 risk on older releases

Task A.2 from `2026-09-08-task-750-compat.md`, done offline from source on 2026-09-08.
The 7.52 transport 406 (fixed) was one instance of a general class: the Go client hard-codes
`application/vnd.sap.adt.*.vN+xml` versions in `Accept`/`Content-Type`, and an older NetWeaver
that only implements `vN-1` answers **406** (Accept) or rejects the body. Every hard-coded
version is a candidate; the ones without a fallback are the exposed ones.

Method: `grep vnd.sap.adt…vN` over `pkg/adt/*.go` (non-test). "Fallback" = the header lists a
second, older version with `q=` (the shape of the shipped 406 fix in `transport.go`).

## Exposed: single version, no fallback — fix candidates

| where | endpoint / use | content-type | dir | risk |
|---|---|---|---|---|
| workflows_function.go:140 | **create FM** body | functions.fmodules.**v3** | Content-Type (W) | HIGH — v3 is newest; 7.50 likely has v2 only |
| crud.go:1260/1261 | **create table** body+accept | tables.**v2** | C-T + Accept (W) | HIGH — write path; #79 probe tests it live on 7.52 |
| client.go:370/391/526 | GetObjectStructure | objectstructure.**v2** | Accept (R) | MED — structure reads used widely |
| client.go:478 | GetFunctionGroup (FM list) | functions.groups.**v2** | Accept (R) | MED — compat.go already probes v3/v2, so it varies |
| cds_tools.go:151 | DDLS (CDS) source | ddic.ddlsources.**v2** | Accept (R) | MED |
| i18n.go:112 | data element labels | dataelements.**v2** | Accept (R) | MED — i18n already flagged broken/dead by author sweep |
| cds.go:50 | CDS codegen data | codegen.data.v1 | Accept (R) | LOW — v1 |
| client.go:2424 | API release state | apirelease.**v10** | Accept (R) | LOW-MED — v10 is high; older may differ |

## Already has a fallback (the good pattern)

- transport.go:80/61-62 — `transportorganizertree.v1, transportorganizer.v1;q=0.9` (the 406 fix).
- 3 more `q=` sites (grep `Accept.*q=`), incl. GetUserTransports.

## The systemic root (not one bug)

`compat.go` can ask the system which versions it supports (it probes functions.groups v3→v2,
objectstructure v2, nodestructure v1, packages v1, transportorganizertree v1). But the runtime
handlers **do not consult compat** — they hard-code a version. So the 406 fix patched one call;
the same failure mode is latent in the eight rows above.

Two ways to close it, cheapest first:
1. **Per-call Accept fallback** (`v_new, v_old;q=0.9`) on the eight endpoints — mechanical, same
   shape as the transport fix. Only touch a row after a live 7.50 run confirms it 406s (don't
   change working calls blind).
2. **Consult compat once at connect** and pick the version — correct but larger; a follow-up.

## How to confirm on live 7.50 (task B)

`vsp -s <750> compat` dumps supported versions → diff against this list. Any endpoint whose
hard-coded version is above what compat reports = a real 406 waiting. On 7.52 the write sweep's
`#79 tabl.create` already exercises `tables.v2`; watch its verdict.
