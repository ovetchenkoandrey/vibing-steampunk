# SAP() capability map — every branch reachable through the hyperfocused tool

**Source of truth:** the route chain in `internal/mcp/handlers_universal.go` (`handleUniversalTool`), read together with the 31 `route*Action` functions it lists and the handlers they dispatch to. Derived offline from source on **2026-09-08**; nothing was executed against a system.

How to read the table:

- `how to call` is copy-pasteable: `action=…, target=…, params={…}`. Required params come first; optional ones after `;`. `target` is parsed as `TYPE NAME` and **both halves are upper-cased** by `parseTarget`.
- `R/W`: R = read-only against SAP (may still write a local file, noted); W = changes SAP state (create/edit/delete/activate/install/deploy/transport/breakpoint/lock/debug-session/run report/execute code).
- `oracle`: an independent way to verify a W row's effect that bypasses the tool's own answer (free SQL via `action="query"` on TADIR/TDEVC/TRDIR/DD02L/E070/E071/DWINACTIV etc., an ADT read through a different route, or RFC `op=call`). `—` for R rows.
- `reach / answer / verdict / cause` are intentionally empty — later live runs fill them.
- Chain order matters: the first route that returns `handled=true` wins. Rows that are claimed by a route but can never be reached because an earlier route claims the same call are marked **SHADOWED** in the handler column (see "Static observations").

## Capability matrix

| # | route | how to call (action / target / params) | R/W | handler | oracle | reach | answer | verdict | cause |
|---|---|---|---|---|---|---|---|---|---|
| 1 | (pre-chain) | `action=""` or `action="info"` — no target, no params | R | handleInfo | — | | | | |
| 2 | (pre-chain) | `action="help"`; optional `target="tips"` (any help topic) | R | handleHelp | — | | | | |
| 3 | routeSourceAction | `action="read", target="CLAS ZCL_X"`; params `include`, `method`, `include_context`(bool, default true), `max_deps` | R | handleGetSource | — | | | | |
| 4 | routeSourceAction | `action="read", target="PROG ZPROG"`; `include_context`, `max_deps` | R | handleGetSource | — | | | | |
| 5 | routeSourceAction | `action="read", target="INTF ZIF_X"` | R | handleGetSource | — | | | | |
| 6 | routeSourceAction | `action="read", target="FUNC Z_FM", params={"parent":"ZFUGR"}` | R | handleGetSource | — | | | | |
| 7 | routeSourceAction | `action="read", target="FUGR ZFUGR"` | R | handleGetSource | — | | | | |
| 8 | routeSourceAction | `action="read", target="INCL ZINCL"` | R | handleGetSource | — | | | | |
| 9 | routeSourceAction | `action="read", target="DDLS ZI_VIEW"` | R | handleGetSource | — | | | | |
| 10 | routeSourceAction | `action="read", target="BDEF ZI_BO"` | R | handleGetSource | — | | | | |
| 11 | routeSourceAction | `action="read", target="SRVD ZSD_X"` | R | handleGetSource | — | | | | |
| 12 | routeSourceAction | `action="read", target="MSAG ZMSG"` | R | handleGetSource | — | | | | |
| 13 | routeSourceAction | `action="read", target="VIEW ZV_X"` | R | handleGetSource | — | | | | |
| 14 | routeSourceAction | `action="edit", target="CLAS ZCL_X", params={"source":"..."}`; `mode`(upsert/create/update), `description`, `package`, `test_source`, `transport`, `method` | W | handleWriteSource | `read CLAS ZCL_X` (include_context=false) equals source; SQL `SELECT * FROM TADIR WHERE OBJECT='CLAS' AND OBJ_NAME='ZCL_X'`; `SELECT * FROM DWINACTIV WHERE OBJ_NAME='ZCL_X'` empty after activation; VRSD new version | | | | |
| 15 | routeSourceAction | `action="edit", target="PROG ZPROG", params={"source":"..."}`; same options | W | handleWriteSource | `read PROG`; SQL TRDIR (NAME), REPOSRC; DWINACTIV empty | | | | |
| 16 | routeSourceAction | `action="edit", target="INTF ZIF_X", params={"source":"..."}` | W | handleWriteSource | `read INTF`; SQL SEOCLASS (CLSNAME, CLSTYPE=1); TADIR | | | | |
| 17 | routeSourceAction | `action="edit", target="FUNC Z_FM", params={"source":"...","parent":"ZFUGR"}` | W | handleWriteSource | `read FUNC` w/ parent; SQL TFDIR (FUNCNAME, PNAME) | | | | |
| 18 | routeSourceAction | `action="edit", target="DDLS ZI_VIEW", params={"source":"..."}` | W | handleWriteSource | `read DDLS`; SQL DDDDLSRC (DDLNAME, SOURCE); DDLDEPENDENCY | | | | |
| 19 | routeSourceAction | `action="edit", target="BDEF ZI_BO", params={"source":"..."}` | W | handleWriteSource | `read BDEF`; TADIR OBJECT='BDEF' | | | | |
| 20 | routeSourceAction | `action="edit", target="SRVD ZSD_X", params={"source":"..."}` | W | handleWriteSource | `read SRVD`; TADIR OBJECT='SRVD' | | | | |
| 21 | routeSourceAction | `action="edit", target="MSAG ZMSG", params={"source":"..."}` | W | handleWriteSource | `read MSAG`; SQL T100 (ARBGB='ZMSG'); T100A | | | | |
| 22 | routeSourceAction | `action="edit", target="TABL ZTAB", params={"source":"..."}` | W | handleWriteSource | `read TABL ZTAB`; SQL DD02L (TABNAME, AS4LOCAL='A'), DD03L fields | | | | |
| 23 | routeSourceAction | `action="edit", target="EDITSOURCE", params={"object_url":"/sap/bc/adt/oo/classes/zcl_x","old_string":"a","new_string":"b"}`; `replace_all`, `syntax_check`, `case_insensitive`, `method`, `ignore_warnings`, `transport` | W | handleEditSource | `read CLAS …` shows replacement; DWINACTIV empty; VRSD | | | | |
| 24 | routeReadAction | `action="read", target="PROG ZPROG"` | R | handleGetProgram — **SHADOWED** by #4 (routeSourceAction claims read PROG first) | — | | | | |
| 25 | routeReadAction | `action="read", target="CLAS ZCL_X"` | R | handleGetClass — **SHADOWED** by #3 | — | | | | |
| 26 | routeReadAction | `action="read", target="INTF ZIF_X"` | R | handleGetInterface — **SHADOWED** by #5 | — | | | | |
| 27 | routeReadAction | `action="read", target="FUNC Z_FM", params={"parent":"ZFUGR"}` | R | handleGetFunction — **SHADOWED** by #6 | — | | | | |
| 28 | routeReadAction | `action="read", target="FUGR ZFUGR"` (JSON: FM list) | R | handleGetFunctionGroup — **SHADOWED** by #7 | — | | | | |
| 29 | routeReadAction | `action="read", target="INCL ZINCL"` | R | handleGetInclude — **SHADOWED** by #8 | — | | | | |
| 30 | routeReadAction | `action="read", target="MSAG ZMSG"` (SE91 message list) | R | handleGetMessages — **SHADOWED** by #12 | — | | | | |
| 31 | routeReadAction | `action="read", target="TABL ZTAB"` | R | handleGetTable | — | | | | |
| 32 | routeReadAction | `action="read", target="DEVC $ZDEV"` | R | handleGetPackage | — | | | | |
| 33 | routeReadAction | `action="read", target="TRAN SE80"` | R | handleGetTransaction | — | | | | |
| 34 | routeReadAction | `action="read", target="TYPE_INFO MATNR"` | R | handleGetTypeInfo | — | | | | |
| 35 | routeReadAction | `action="read", target="STRUCT ZSTRUCT"` | R | handleGetStructure | — | | | | |
| 36 | routeReadAction | `action="read", target="CDS_DEPS ZI_VIEW"`; `dependency_level`(unit/hierarchy), `with_associations`, `context_package` | R | handleGetCDSDependencies | — | | | | |
| 37 | routeReadAction | `action="read", target="CDS_IMPACT ZI_VIEW"` | R | handleGetCDSImpactAnalysis | — | | | | |
| 38 | routeReadAction | `action="read", target="CDS_ELEMENTS ZI_VIEW"` | R | handleGetCDSElementInfo | — | | | | |
| 39 | routeReadAction | `action="read", target="TABL_CONTENTS T000"`; `max_rows`, `sql_query` | R | handleGetTableContents | — | | | | |
| 40 | routeReadAction | `action="read", target="COVERAGE /sap/bc/adt/oo/classes/zcl_x"`; `include_dangerous`, `include_long` (runs unit tests with coverage; target is upper-cased — see observations) | R | handleGetCodeCoverage | — | | | | |
| 41 | routeReadAction | `action="read", target="CHECK_RUN <check_run_id>"` | R | handleGetCheckRunResults | — | | | | |
| 42 | routeReadAction | `action="read", target="API_STATE /sap/bc/adt/oo/classes/cl_abap_typedescr"` (URI upper-cased by parseTarget) | R | handleGetAPIReleaseState | — | | | | |
| 43 | routeReadAction | `action="query", target="TABL_CONTENTS T000", params={"max_rows":50}`; `sql_query`/`sql`/`query` | R | handleGetTableContents | — | | | | |
| 44 | routeReadAction | `action="query", params={"sql":"SELECT * FROM T000"}` (target empty or `"SQL"`); `sql_query`/`query` aliases; `max_rows` | R | handleRunQuery | — | | | | |
| 45 | routeReadAction | `action="query", target="SQL T000"` (no sql → table contents of the named table; `max_rows`) | R | handleGetTableContents | — | | | | |
| 46 | routeReadAction | `action="query"` with nothing usable (e.g. `target="TABL T000"` without sql) | R | needParams("query") guidance | — | | | | |
| 47 | routeSearchAction | `action="search", target="ZCL_*"` (target text is the query; `TYPE NAME` is joined with a space); `maxResults`/`max_results` | R | handleSearchObject | — | | | | |
| 48 | routeSearchAction | `action="search", params={"query":"ZCL_*"}` (no target) | R | handleSearchObject | — | | | | |
| 49 | routeGrepAction | `action="grep", params={"object_urls":["/sap/bc/adt/oo/classes/zcl_x"],"pattern":"SELECT"}`; `case_insensitive`, `context_lines` | R | handleGrepObjects | — | | | | |
| 50 | routeGrepAction | `action="grep", params={"packages":["$TMP"],"pattern":"SELECT"}`; `include_subpackages`, `object_types`[], `case_insensitive`, `max_results` | R | handleGrepPackages | — | | | | |
| 51 | routeGrepAction | `action="grep", params={"package":"$TMP","pattern":"SELECT"}` (`package_name` alias); `object_types` csv, `case_insensitive`, `max_results` | R | handleGrepPackage | — | | | | |
| 52 | routeGrepAction | `action="grep", params={"object_url":"/sap/bc/adt/oo/classes/zcl_x","pattern":"TODO"}` (`object` alias); `case_insensitive`, `context_lines` | R | handleGrepObject | — | | | | |
| 53 | routeGrepAction | `action="grep"` with none of the four selectors | R | needParams("grep") guidance | — | | | | |
| 54 | routeCodeIntelAction | `action="analyze", params={"type":"definition","source_url":"…/source/main","source":"…","line":10,"start_column":5,"end_column":12}`; `implementation`, `main_program` | R | handleFindDefinition | — | | | | |
| 55 | routeCodeIntelAction | `action="analyze", params={"type":"references","object_url":"/sap/bc/adt/oo/classes/zcl_x"}`; `line`, `column`, `max_results` | R | handleFindReferences | — | | | | |
| 56 | routeCodeIntelAction | `action="analyze", params={"type":"completion","source_url":"…","source":"…","line":1,"column":1}` | R | handleCodeCompletion | — | | | | |
| 57 | routeCodeIntelAction | `action="analyze", params={"type":"pretty_print","source":"…"}` | R | handlePrettyPrint | — | | | | |
| 58 | routeCodeIntelAction | `action="analyze", params={"type":"get_pretty_printer_settings"}` | R | handleGetPrettyPrinterSettings | — | | | | |
| 59 | routeCodeIntelAction | `action="analyze", params={"type":"set_pretty_printer_settings","indentation":true,"style":"keywordUpper"}` | W | handleSetPrettyPrinterSettings | `analyze type=get_pretty_printer_settings` reads back the user setting (RSEUMOD user parameters) | | | | |
| 60 | routeCodeIntelAction | `action="analyze", params={"type":"type_hierarchy","source_url":"…","source":"…","line":1,"column":1}`; `super_types` | R | handleGetTypeHierarchy | — | | | | |
| 61 | routeCodeIntelAction | `action="analyze", params={"type":"class_components","class_url":"/sap/bc/adt/oo/classes/zcl_x"}` | R | handleGetClassComponents | — | | | | |
| 62 | routeCodeIntelAction | `action="analyze", params={"type":"inactive_objects"}` | R | handleGetInactiveObjects | — | | | | |
| 63 | routeCodeIntelAction | `action="analyze", params={"type":"abap_help","keyword":"SELECT"}` (WS ZADT_VSP docs if present) | R | handleGetAbapHelp | — | | | | |
| 64 | routeDevToolsAction | `action="test", params={"object_url":"/sap/bc/adt/oo/classes/zcl_x"}` (`type` empty or `"unit"`); `include_dangerous`, `include_long` — without object_url the route declines and the call falls off the chain | R | handleRunUnitTests | — | | | | |
| 65 | routeDevToolsAction | `action="analyze", params={"type":"syntax_check","object_url":"…","content":"…"}` | R | handleSyntaxCheck | — | | | | |
| 66 | routeDevToolsAction | `action="analyze", params={"type":"execute_abap","code":"lv_result = 'x'."}`; `risk_level`, `return_variable`, `keep_program`, `program_prefix` | W | handleExecuteABAP | temp program: with `keep_program=true` SQL `SELECT NAME FROM TRDIR WHERE NAME LIKE 'ZTEMP_EXEC_%'`; otherwise assert it is gone afterwards; TADIR | | | | |
| 67 | routeDevToolsAction | `action="edit", target="ACTIVATE", params={"object_url":"/sap/bc/adt/programs/programs/ZPROG","object_name":"ZPROG"}` | W | handleActivate | SQL `SELECT * FROM DWINACTIV WHERE OBJ_NAME='ZPROG'` empty; `analyze type=inactive_objects` no longer lists it; VRSD | | | | |
| 68 | routeDevToolsAction | `action="edit", target="ACTIVATE_PACKAGE", params={"package":"$ZDEV","max_objects":100}` (empty package = all inactive of user) | W | handleActivatePackage | DWINACTIV count for the package before/after; `analyze type=inactive_objects` | | | | |
| 69 | routeATCAction | `action="test", params={"type":"atc","object_url":"/sap/bc/adt/oo/classes/zcl_x"}`; `variant`, `max_results` | R | handleRunATCCheck | — | | | | |
| 70 | routeATCAction | `action="test", params={"type":"atc_customizing"}` | R | handleGetATCCustomizing | — | | | | |
| 71 | routeCRUDAction | `action="edit", target="LOCK", params={"object_url":"/sap/bc/adt/programs/programs/ZPROG"}`; `access_mode` (MODIFY/READ) | W | handleLockObject | second LOCK on same object fails; `rfc op=call ENQUEUE_READ` lists the ESR lock (SM12); UNLOCK with returned handle succeeds | | | | |
| 72 | routeCRUDAction | `action="edit", target="UNLOCK", params={"object_url":"…","lock_handle":"…"}` | W | handleUnlockObject | `rfc op=call ENQUEUE_READ` no longer lists the lock; a fresh LOCK succeeds | | | | |
| 73 | routeCRUDAction | `action="edit", target="UPDATE_SOURCE", params={"object_url":"…","source":"…","lock_handle":"…"}`; `transport` | W | handleUpdateSource | `read <TYPE NAME>` returns new source (inactive version until ACTIVATE); DWINACTIV row appears | | | | |
| 74 | routeCRUDAction | `action="edit", target="MOVE", params={"object_type":"CLAS","object_name":"ZCL_X","new_package":"$ZNEW"}` (needs ZADT_VSP WS) | W | handleMoveObject | SQL `SELECT DEVCLASS FROM TADIR WHERE OBJECT='CLAS' AND OBJ_NAME='ZCL_X'` = $ZNEW | | | | |
| 75 | routeCRUDAction | `action="edit", target="COMPARE_SOURCE", params={"type1":"CLAS","name1":"ZCL_A","type2":"CLAS","name2":"ZCL_B"}`; `include1/2`, `parent1/2` | R | handleCompareSource | — | | | | |
| 76 | routeCRUDAction | `action="edit", target="RECOVER_FAILED_CREATE", params={"object_type":"CLAS","name":"ZCL_ZOMBIE","package_name":"$TMP"}`; `parent_name`, `transport` | W | handleRecoverFailedCreate | TADIR row for the object gone; `search ZCL_ZOMBIE` empty; ENQUEUE_READ shows no stale lock | | | | |
| 77 | routeCRUDAction | `action="create", target="OBJECT", params={"object_type":"CLAS/OC","name":"ZCL_NEW","description":"d","package_name":"$TMP"}`; `transport`, `parent_name`(FUGR/FF), `rfc_enabled`+`source` (FUGR/FF → CreateFunctionModule flow), `service_definition`/`binding_version`/`binding_category` (SRVB) | W | handleCreateObject | TADIR row (PGMID R3TR, OBJECT, OBJ_NAME, DEVCLASS); type-specific: TRDIR (PROG), SEOCLASS (CLAS/INTF), TFDIR (FUNC; FMODE='R' when rfc_enabled), TDEVC (DEVC), DDDDLSRC (DDLS) | | | | |
| 78 | routeCRUDAction | `action="create", target="DEVC", params={"name":"$ZNEWPKG","description":"d"}`; `parent`, `transport` (required for non-$), `software_component` | W | handleCreatePackage | SQL `SELECT * FROM TDEVC WHERE DEVCLASS='$ZNEWPKG'`; TADIR OBJECT='DEVC'; `read DEVC $ZNEWPKG` | | | | |
| 79 | routeCRUDAction | `action="create", target="TABL", params={"name":"ZTAB","description":"d","fields":"[{\"name\":\"ID\",\"type\":\"CHAR32\",\"key\":true}]"}` (fields is a JSON *string*); `package`(default $TMP), `transport`, `delivery_class` | W | handleCreateTable | SQL DD02L (TABNAME='ZTAB', AS4LOCAL='A'), DD03L field rows, TADIR OBJECT='TABL'; `read TABL ZTAB` | | | | |
| 80 | routeCRUDAction | `action="create", target="CLONE", params={"object_type":"CLAS","source_name":"ZCL_A","target_name":"ZCL_B","package":"$TMP"}` | W | handleCloneObject | TADIR row for ZCL_B; `read CLAS ZCL_B` source mentions ZCL_B not ZCL_A | | | | |
| 81 | routeCRUDAction | `action="delete", target="OBJECT" (or no target), params={"object_url":"/sap/bc/adt/programs/programs/ZPROG","lock_handle":"…"}`; `transport` | W | handleDeleteObject | TADIR row gone; `search ZPROG` empty; TRDIR row gone | | | | |
| 82 | routeCRUDAction | `action="read", target="CLASS_INFO ZCL_X"` | R | handleGetClassInfo | — | | | | |
| 83 | routeClassIncludeAction | `action="read", target="CLAS_INCLUDE ZCL_X", params={"include_type":"testclasses"}` (definitions/implementations/macros/testclasses) | R | handleGetClassInclude | — | | | | |
| 84 | routeClassIncludeAction | `action="create", target="CLAS_TEST_INCLUDE", params={"class_name":"ZCL_X","lock_handle":"…"}`; `transport` | W | handleCreateTestInclude | `read CLAS_INCLUDE ZCL_X include_type=testclasses` succeeds; SQL `SELECT NAME FROM TRDIR WHERE NAME='ZCL_X=====CCAU'` (padded include name) | | | | |
| 85 | routeClassIncludeAction | `action="edit", target="CLAS_INCLUDE", params={"class_name":"ZCL_X","include_type":"testclasses","source":"…","lock_handle":"…"}`; `transport` | W | handleUpdateClassInclude | `read CLAS_INCLUDE …` returns new source; DWINACTIV row | | | | |
| 86 | routeWorkflowAction | `action="edit", params={"type":"write_program","program_name":"ZPROG","source":"…"}`; `transport` | W | handleWriteProgram | `read PROG ZPROG`; TRDIR/TADIR; DWINACTIV empty (auto-activates) | | | | |
| 87 | routeWorkflowAction | `action="edit", params={"type":"write_class","class_name":"ZCL_X","source":"…"}`; `transport` | W | handleWriteClass | `read CLAS ZCL_X`; SEOCLASS/TADIR; DWINACTIV empty | | | | |
| 88 | routeWorkflowAction | `action="create", target="PROGRAM", params={"program_name":"ZPROG","description":"d","package_name":"$TMP","source":"…"}`; `transport` | W | handleCreateAndActivateProgram | TADIR + TRDIR row; `read PROG`; DWINACTIV empty | | | | |
| 89 | routeWorkflowAction | `action="create", target="CLASS_WITH_TESTS", params={"class_name":"ZCL_X","description":"d","package_name":"$TMP","class_source":"…","test_source":"…"}`; `transport` | W | handleCreateClassWithTests | TADIR row; `read CLAS_INCLUDE … testclasses`; `test object_url=…` runs | | | | |
| 90 | routeFileIOAction | `action="system"` or `action="edit"`, `params={"type":"deploy_from_file","file_path":"C:/x/zcl_x.clas.abap","package_name":"$TMP"}`; `transport` | W | handleDeployFromFile | TADIR row; `read <TYPE NAME>` equals file content; DWINACTIV empty | | | | |
| 91 | routeFileIOAction | `action="system"` or `"edit"`, `params={"type":"save_to_file","object_type":"CLAS","object_name":"ZCL_X","output_dir":"C:/out"}` (aliases `objType`/`objectName`/`outputPath`); `include`, `parent`/`function_group`/`parentName` | R (writes local file) | handleSaveToFile | — | | | | |
| 92 | routeFileIOAction | `action="system"` or `"edit"`, `params={"type":"rename","objType":"CLAS/OC","oldName":"ZCL_A","newName":"ZCL_B","packageName":"$TMP"}`; `transport` | W | handleRenameObject | TADIR: OBJ_NAME='ZCL_A' gone, 'ZCL_B' present; `search ZCL_A` empty | | | | |
| 93 | routeDebuggerAction | `action="debug", target="SET_BREAKPOINT", params={"kind":"line","program":"ZCL_X","line":42}` (kind default line); `condition` | W | handleSetBreakpoint | `debug GET_BREAKPOINTS` (same session only); ZADT_VSP `get_all_breakpoints`; functional: `debug LISTEN` catches a stop when the line runs in another session | | | | |
| 94 | routeDebuggerAction | `action="debug", target="SET_BREAKPOINT", params={"kind":"statement","statement":"SELECT"}` | W | handleSetBreakpoint | as #93 | | | | |
| 95 | routeDebuggerAction | `action="debug", target="SET_BREAKPOINT", params={"kind":"exception","exception":"CX_SY_ZERODIVIDE"}` | W | handleSetBreakpoint | as #93 | | | | |
| 96 | routeDebuggerAction | `action="debug", target="GET_BREAKPOINTS"` | R | handleGetBreakpoints | — | | | | |
| 97 | routeDebuggerAction | `action="debug", target="DELETE_BREAKPOINT", params={"breakpoint_id":"<id>"}` | W | handleDeleteBreakpoint | GET_BREAKPOINTS no longer lists id; LISTEN no longer stops there | | | | |
| 98 | routeDebuggerAction | `action="debug", target="DELETE_BREAKPOINT", params={"breakpoint_id":"all"}` | W | handleDeleteBreakpoint | GET_BREAKPOINTS empty | | | | |
| 99 | routeDebuggerAction | `action="debug", target="CALL_RFC", params={"function":"RFC_PING","params":"{\"IV_X\":\"1\"}"}` (params is a JSON *string*; needs ZADT_VSP WS) | W (executes FM) | handleCallRFC | FM-specific side effect; cross-check the same call via `action="rfc", op=call` (gateway path) | | | | |
| 100 | routeDebuggerAction | `action="debug", target="MOVE", params={"object_type":"CLAS","object_name":"ZCL_X","new_package":"$ZNEW"}` (same handler as #74) | W | handleMoveObject | TADIR.DEVCLASS | | | | |
| 101 | routeDebuggerLegacyAction | `action="debug", target="LISTEN"`; `user`, `timeout`(≤240s) — blocking, attaches on stop | W (debug session) | handleDebuggerListen | `debug GET_STACK` answers afterwards; SM50/SM04 shows the debuggee stopped | | | | |
| 102 | routeDebuggerLegacyAction | `action="debug", target="ATTACH", params={"debuggee_id":"…"}`; `user` | W (debug session) | handleDebuggerAttach | `debug GET_STACK` works | | | | |
| 103 | routeDebuggerLegacyAction | `action="debug", target="DETACH"` | W (debug session) | handleDebuggerDetach | `debug GET_STACK` reports no session; debuggee continues (SM50) | | | | |
| 104 | routeDebuggerLegacyAction | `action="debug", target="STEP", params={"step_type":"stepOver"}` (stepInto/stepOver/stepReturn/stepContinue/stepRunToLine/stepJumpToLine/terminateDebuggee) | W (debug session) | handleDebuggerStep | GET_STACK top-frame line changes | | | | |
| 105 | routeDebuggerLegacyAction | `action="debug", target="GET_STACK"` | R | handleDebuggerGetStack | — | | | | |
| 106 | routeDebuggerLegacyAction | `action="debug", target="GET_VARIABLES"`; `variable_ids`[] (empty = locals; one `@id` = expand; names = read) | R | handleDebuggerGetVariables | — | | | | |
| 107 | routeAMDPADTAction | `action="debug", target="AMDP_ADT_START"`; `user` | W (debug session) | amdpADTStart (via wrapAMDP) | AMDP_ADT_AWAIT answers; HANA `M_CONNECTIONS`/debug session visible via `query` on HANA monitoring if exposed | | | | |
| 108 | routeAMDPADTAction | `action="debug", target="AMDP_ADT_BREAKPOINT", params={"class":"ZCL_AMDP","line":12}` | W | amdpADTBreakpoint | AMDP_ADT_AWAIT reports breakpoint state VALID/INVALID | | | | |
| 109 | routeAMDPADTAction | `action="debug", target="AMDP_ADT_AWAIT"`; `max_events`(default 12) | R | amdpADTAwait | — | | | | |
| 110 | routeAMDPADTAction | `action="debug", target="AMDP_ADT_STOP"` | W (debug session) | amdpADTStop | subsequent AMDP_ADT_AWAIT fails / START succeeds again | | | | |
| 111 | routeAMDPAction | `action="debug", target="AMDP_START"`; `cascade_mode`(FULL) — WebSocket ZADT_VSP route | W (debug session) | handleAMDPDebuggerStart | second START errors "already active"; AMDP_STOP succeeds | | | | |
| 112 | routeAMDPAction | `action="debug", target="AMDP_RESUME"` | W (debug session) | handleAMDPDebuggerResume | event list; AMDP_GET_VARIABLES after on_break | | | | |
| 113 | routeAMDPAction | `action="debug", target="AMDP_STOP"` | W (debug session) | handleAMDPDebuggerStop | AMDP_RESUME errors "no active session" | | | | |
| 114 | routeAMDPAction | `action="debug", target="AMDP_STEP", params={"step_type":"…"}` | W (debug session) | handleAMDPDebuggerStep | AMDP_GET_VARIABLES / position change | | | | |
| 115 | routeAMDPAction | `action="debug", target="AMDP_GET_VARIABLES"` | R | handleAMDPGetVariables | — | | | | |
| 116 | routeAMDPAction | `action="debug", target="AMDP_SET_BREAKPOINT", params={"proc_name":"…","line":5}` | W | handleAMDPSetBreakpoint | AMDP_GET_BREAKPOINTS lists it | | | | |
| 117 | routeAMDPAction | `action="debug", target="AMDP_GET_BREAKPOINTS"` | R | handleAMDPGetBreakpoints | — | | | | |
| 118 | routeUI5Action | any action, `params={"type":"ui5_list_apps"}`; `query`, `max_results` | R | handleUI5ListApps | — | | | | |
| 119 | routeUI5Action | any action, `params={"type":"ui5_get_app","app_name":"ZAPP"}` | R | handleUI5GetApp | — | | | | |
| 120 | routeUI5Action | any action, `params={"type":"ui5_get_file","app_name":"ZAPP","file_path":"Component.js"}` | R | handleUI5GetFileContent | — | | | | |
| 121 | routeUI5Action | any action, `params={"type":"ui5_upload_file","app_name":"ZAPP","file_path":"x.js","content":"…"}`; `content_type` | W | handleUI5UploadFile | `read UI5_FILE` returns content; SQL SMIMLOIO/SMIMPHIO (MIME repo) rows for the path | | | | |
| 122 | routeUI5Action | any action, `params={"type":"ui5_delete_file","app_name":"ZAPP","file_path":"x.js"}` | W | handleUI5DeleteFile | `read UI5_APP ZAPP` file list; SMIMLOIO row gone | | | | |
| 123 | routeUI5Action | any action, `params={"type":"ui5_create_app","app_name":"ZAPP","package":"$TMP"}`; `description`, `transport` | W | handleUI5CreateApp | SQL `SELECT * FROM O2APPL WHERE APPLNAME='ZAPP'`; TADIR OBJECT='WAPA' | | | | |
| 124 | routeUI5Action | any action, `params={"type":"ui5_delete_app","app_name":"ZAPP"}`; `transport` | W | handleUI5DeleteApp | O2APPL / TADIR WAPA row gone | | | | |
| 125 | routeUI5Action | `action="read", target="UI5_LIST"`; `query`, `max_results` | R | handleUI5ListApps | — | | | | |
| 126 | routeUI5Action | `action="read", target="UI5_APP ZAPP"` (app_name from target) | R | handleUI5GetApp | — | | | | |
| 127 | routeUI5Action | `action="read", target="UI5_FILE", params={"app_name":"ZAPP","file_path":"Component.js"}` | R | handleUI5GetFileContent | — | | | | |
| 128 | routeUI5Action | `action="edit", target="UI5_UPLOAD", params={"app_name":"ZAPP","file_path":"x.js","content":"…"}` | W | handleUI5UploadFile | as #121 | | | | |
| 129 | routeUI5Action | `action="delete", target="UI5_FILE", params={"app_name":"ZAPP","file_path":"x.js"}` | W | handleUI5DeleteFile | as #122 | | | | |
| 130 | routeUI5Action | `action="create", target="UI5_APP", params={"app_name":"ZAPP","package":"$TMP"}` | W | handleUI5CreateApp | as #123 | | | | |
| 131 | routeUI5Action | `action="delete", target="UI5_APP", params={"app_name":"ZAPP"}` | W | handleUI5DeleteApp | as #124 | | | | |
| 132 | routeTransportAction | `action="system", params={"type":"list_transports"}`; `user` | R | handleListTransports | — | | | | |
| 133 | routeTransportAction | `action="system", params={"type":"get_transport","transport":"A4HK900123"}` | R | handleGetTransport | — | | | | |
| 134 | routeTransportAction | `action="system", params={"type":"create_transport","description":"d","package":"ZPKG"}`; `transport_layer`, `type` (note: `type` is also the selector) | W | handleCreateTransport | SQL `SELECT TRKORR,TRFUNCTION,TRSTATUS FROM E070 WHERE TRKORR='<new>'` (TRSTATUS='D'); E07T description; task row with STRKORR | | | | |
| 135 | routeTransportAction | `action="system", params={"type":"release_transport","transport":"A4HK900123"}`; `ignore_locks`, `skip_atc` | W | handleReleaseTransport | E070.TRSTATUS='R' for request and tasks; E071 object list; TMS queue | | | | |
| 136 | routeTransportAction | `action="system", params={"type":"delete_transport","transport":"A4HK900123"}` | W | handleDeleteTransport | E070 row gone (and tasks); E071 empty | | | | |
| 137 | routeTransportAction | `action="system", params={"type":"get_user_transports","user_name":"DEVELOPER"}` | R | handleGetUserTransports | — | | | | |
| 138 | routeTransportAction | `action="system", params={"type":"get_transport_info","object_url":"…","dev_class":"ZPKG"}` | R | handleGetTransportInfo | — | | | | |
| 139 | routeTransportAction | `action="system", params={"type":"execute_abap","code":"…"}` (same handler as #66) | W | handleExecuteABAP | as #66 | | | | |
| 140 | routeGitAction | `action="system", params={"type":"git_types"}` (ZADT_VSP WS) | R | handleGitTypes | — | | | | |
| 141 | routeGitAction | `action="system", params={"type":"git_export","packages":"$ZDEV"}` (csv) or `"objects":"[{…}]"` (JSON string); `include_subpackages`, `output_dir` | R (writes local ZIP) | handleGitExport | — | | | | |
| 142 | routeReportAction | `action="debug", target="RUN_REPORT", params={"report":"ZREPORT"}`; `variant`, `params` (JSON string) — schedules a background job, polls ≤60s, reads spool (ZADT_VSP WS) | W (runs report) | handleRunReport | SQL TBTCO (JOBNAME, STATUS='F'), TBTCP; spool TSP01; the report's own DB effect | | | | |
| 143 | routeReportAction | `action="debug", target="RUN_REPORT_ASYNC", params={"report":"ZREPORT"}`; `variant`, `params` | W (runs report) | handleRunReportAsync | TBTCO job row; GET_ASYNC_RESULT | | | | |
| 144 | routeReportAction | `action="debug", target="GET_ASYNC_RESULT", params={"task_id":"…"}`; `wait` | R | handleGetAsyncResult | — | | | | |
| 145 | routeReportAction | `action="debug", target="GET_VARIANTS", params={"report":"ZREPORT"}` | R | handleGetVariants | — | | | | |
| 146 | routeReportAction | `action="debug", target="GET_TEXT_ELEMENTS", params={"program":"ZREPORT"}`; `language` | R | handleGetTextElements | — | | | | |
| 147 | routeReportAction | `action="debug", target="SET_TEXT_ELEMENTS", params={"program":"ZREPORT","text_symbols":{"001":"Hello"}}`; `language`, `selection_texts`, `heading_texts` (≥1 of the three) | W | handleSetTextElements | independent ADT path: `i18n op=text_pool program_name=ZREPORT language=EN`; GET_TEXT_ELEMENTS | | | | |
| 148 | routeInstallAction | `action="system", params={"type":"install_zadt_vsp"}`; `package`, `skip_git_service`, `check_only` (check_only=true is read-only) | W | handleInstallZADTVSP | TADIR rows for ZCL_ADT_VSP* / package objects; SQL ICFSERVICE for the SICF node; `system FEATURES` probe flips; `system git_types` answers | | | | |
| 149 | routeInstallAction | `action="system", params={"type":"install_abapgit","edition":"standalone"}`; `package`, `check_only` | W | handleInstallAbapGit | TADIR R3TR PROG ZABAPGIT_STANDALONE (or dev-edition package contents); `search ZABAPGIT*` | | | | |
| 150 | routeInstallAction | `action="system", params={"type":"install_dummy_test"}`; `check_only`, `cleanup` | W | handleInstallDummyTest | TDEVC `$ZADT_INSTALL_TEST`; TADIR rows ZIF_DUMMY_TEST / ZCL_DUMMY_TEST (gone after cleanup=true) | | | | |
| 151 | routeInstallAction | `action="system", params={"type":"list_dependencies"}` | R | handleListDependencies | — | | | | |
| 152 | routeInstallAction | `action="system", params={"type":"deploy_zip","source":"abapgit-standalone","package":"$ZGIT"}`; `dry_run` (read-only), `type_filter`, `name_filter` | W | handleDeployZip | `SELECT COUNT(*) FROM TADIR WHERE DEVCLASS='$ZGIT'` before/after; `read DEVC $ZGIT` | | | | |
| 153 | routeSystemAction | `action="system", target="INFO"` | R | handleGetSystemInfo | — | | | | |
| 154 | routeSystemAction | `action="system", target="COMPONENTS"` | R | handleGetInstalledComponents | — | | | | |
| 155 | routeSystemAction | `action="system", target="CONNECTION"` | R | handleGetConnectionInfo | — | | | | |
| 156 | routeSystemAction | `action="system", target="FEATURES"` | R | handleGetFeatures | — | | | | |
| 157 | routeRFCAction | `action="rfc", params={"op":"info"}` (also the default with no target) — RFC_SYSTEM_INFO; dest overrides `host`,`sysnr`,`port`,`user` on every rfc op | R | routeRFCAction (inline) | — | | | | |
| 158 | routeRFCAction | `action="rfc", params={"op":"probe"}` — release, components, helper presence, callable FMs | R | routeRFCAction → saprfc.RunProbe | — | | | | |
| 159 | routeRFCAction | `action="rfc", params={"op":"ping"}` — RFC_PING | R | routeRFCAction (inline) | — | | | | |
| 160 | routeRFCAction | `action="rfc", target="STFC_CONNECTION"` (op=describe is the default when a target is given and no args) | R | routeRFCAction → DescribeTool | — | | | | |
| 161 | routeRFCAction | `action="rfc", target="Z_DOUBLE", params={"op":"call","args":{"N":21}}` (op defaults to call when `args` present) | W (executes FM; R for read-only FMs) | routeRFCAction → Client.Call | FM-specific: read the table/object the FM writes via `query`; for BAPIs check BAPI_TRANSACTION_COMMIT semantics | | | | |
| 162 | routeRFCAction | `action="rfc", target="BAPI_USER_*", params={"op":"search"}`; `all` (include non-remote), `top` | R | routeRFCAction → ReadTable TFDIR | — | | | | |
| 163 | routeRFCAction | `action="rfc", target="T000", params={"op":"read_table","fields":["MANDT"],"where":"…","top":5}` (aliases `read-table`, `table`) | R | routeRFCAction → saprfc.ReadTable | — | | | | |
| 164 | routeDumpsAction | `action="analyze", params={"type":"list_dumps"}`; `user`, `error_type`/`exception_type`, `program`, `since`/`from`/`date_from`, `until`/`to`/`date_to`, `max_results`/`top`/`limit` (`package` accepted but ignored, noted) | R | handleListDumps | — | | | | |
| 165 | routeDumpsAction | `action="analyze", params={"type":"group_dumps"}`; same filters | R | handleGroupDumps | — | | | | |
| 166 | routeDumpsAction | `action="analyze", params={"type":"get_dump","dump_id":"latest"}` (`dump`/`which` aliases; default latest; full id skips listing) | R | handleGetDump | — | | | | |
| 167 | routeDumpsAction | `action="analyze", params={"type":"explain_dump","dump_id":"latest"}`; `tolerance` (duration) / `tolerance_minutes`, `matches`/`match_limit` | R | handleExplainDump | — | | | | |
| 168 | routeDumpsAction | `action="analyze", params={"type":"similar_dumps","dump_id":"latest"}`; `deep`/`detail_budget` (default 10) + list filters | R | handleSimilarDumps | — | | | | |
| 169 | routeDumpsAction | `action="analyze", params={"type":"dump_impact","dump_id":"latest"}`; `frames`/`impact_frames`/`max_units`, `top`/`impact_top`/`limit` | R | handleDumpImpact | — | | | | |
| 170 | routeDumpsAction | `action="analyze", params={"type":"application_log"}`; `program`, `user`, `object`/`log_object`, `subobject`/`sub_object`, `since`/`until`, `max_results` | R | handleApplicationLog | — | | | | |
| 171 | routeTracesAction | `action="analyze", params={"type":"list_traces"}`; `user`, `process_type`, `object_type`, `max_results` | R | handleListTraces | — | | | | |
| 172 | routeTracesAction | `action="analyze", params={"type":"get_trace","trace_id":"…"}`; `tool_type` (hitlist/statements/dbAccesses) | R | handleGetTrace | — | | | | |
| 173 | routeSQLTraceAction | `action="analyze", params={"type":"sql_trace_state"}` | R | handleGetSQLTraceState | — | | | | |
| 174 | routeSQLTraceAction | `action="analyze", params={"type":"list_sql_traces"}`; `user`, `max_results` | R | handleListSQLTraces | — | | | | |
| 175 | routeLintAction | `action="lint", params={"object_type":"CLAS","object_name":"ZCL_X"}` or `{"source":"…"}` (offline analyser) | R | handleAnalyzeABAPCode | — | | | | |
| 176 | routeLintAction | `action="analyze", params={"type":"lint","object_type":"CLAS","object_name":"ZCL_X"}` | R | handleAnalyzeABAPCode | — | | | | |
| 177 | routeAnalysisAction | `action="analyze", params={"type":"call_graph","object_type":"CLAS","object_name":"ZCL_X"}` (or `object_uri`); `direction` callers/callees/both, `max_results` | R | handleGetCallGraph | — | | | | |
| 178 | routeAnalysisAction | `action="analyze", params={"type":"object_structure","object_name":"ZCL_X"}`; `max_results` | R | handleGetObjectStructure | — | | | | |
| 179 | routeAnalysisAction | `action="analyze", params={"type":"callers","object_type":"CLAS","object_name":"ZCL_X"}`; `object_uri`, `max_results` | R | handleGetCallersOf | — | | | | |
| 180 | routeAnalysisAction | `action="analyze", params={"type":"callees","object_type":"CLAS","object_name":"ZCL_X"}`; `object_uri`, `max_results`, `include_inactive` (needs free SQL on CROSS/WBCROSSGT) | R | handleGetCalleesOf | — | | | | |
| 181 | routeAnalysisAction | `action="analyze", params={"type":"analyze_call_graph","object_type":"CLAS","object_name":"ZCL_X"}`; `direction` | R | handleAnalyzeCallGraph | — | | | | |
| 182 | routeAnalysisAction | `action="analyze", params={"type":"compare_call_graphs","object_uri":"…","trace_data":"[{…}]"}` | R | handleCompareCallGraphs | — | | | | |
| 183 | routeAnalysisAction | `action="analyze", params={"type":"trace_execution","object_uri":"…"}`; `max_depth`, `run_tests` (runs unit tests when true), `test_object_uri`, `trace_user` | R | handleTraceExecution | — | | | | |
| 184 | routeAnalysisAction | `action="analyze", params={"type":"check_boundaries","package":"$ZDEV"}` (or `object`, or `source` offline); `whitelist`, `depth`, `format` | R | handleCheckBoundaries | — | | | | |
| 185 | routeAnalysisAction | `action="analyze", params={"type":"loads","object_name":"ZCL_X"}`; `direction` | R | handleLoads | — | | | | |
| 186 | routeAnalysisAction | `action="analyze", params={"type":"graph_stats","source":"…"}` (or `object_type`+`object_name`, or `package`) | R | handleGraphStats | — | | | | |
| 187 | routeAnalysisAction | `action="analyze", params={"type":"co_change","object_type":"CLAS","object_name":"ZCL_X"}`; `top_n` | R | handleCoChange | — | | | | |
| 188 | routeAnalysisAction | `action="analyze", params={"type":"impact","object_type":"CLAS","object_name":"ZCL_X"}`; `max_depth`, `include_source_analysis`, `include_co_change`, `edge_kinds` | R | handleImpact | — | | | | |
| 189 | routeAnalysisAction | `action="analyze", params={"type":"where_used_config","variable":"ZKEKEKE"}`; `grep` | R | handleWhereUsedConfig | — | | | | |
| 190 | routeAnalysisAction | `action="analyze", params={"type":"usage_examples","object_type":"CLAS","object_name":"ZCL_X"}`; `method`, `form`, `submit`, `top_n` | R | handleUsageExamples | — | | | | |
| 191 | routeAnalysisAction | `action="analyze", params={"type":"health","package":"$ZDEV"}` (or `object_type`+`object_name`; `parent`) | R | handleHealth | — | | | | |
| 192 | routeAnalysisAction | `action="analyze", params={"type":"cr_history","object_type":"CLAS","object_name":"ZCL_X"}` | R | handleCRHistory | — | | | | |
| 193 | routeAnalysisAction | `action="analyze", params={"type":"tr_boundaries","transports":"A4HK900123,A4HK900124"}` | R | handleTransportBoundaries | — | | | | |
| 194 | routeAnalysisAction | `action="analyze", params={"type":"cr_boundaries","cr_id":"CR-123"}` | R | handleCRBoundaries | — | | | | |
| 195 | routeContextAction | `action="analyze", params={"type":"context","object_type":"CLAS","name":"ZCL_X"}`; `source`, `max_deps`, `depth` | R | handleGetContext | — | | | | |
| 196 | routeContextAction | `action="analyze", params={"type":"parse_abap","source":"…"}` (or `object_type`+`name`) | R | handleParseABAP | — | | | | |
| 197 | routeContextAction | `action="analyze", params={"type":"analyze_deps","source":"…"}` (or `object_type`+`name`) | R | handleAnalyzeDeps | — | | | | |
| 198 | routeContextAction | `action="analyze", params={"type":"effects","object_type":"CLAS","name":"ZCL_X"}` (`object_name` alias; or `source`) | R | handleAnalyzeEffects | — | | | | |
| 199 | routeServiceBindingAction | `action="edit", target="PUBLISH_SERVICE", params={"service_name":"ZSB_X"}`; `service_version`(0001) | W | handlePublishServiceBinding | SQL `/IWFND/I_MED_SRH` (SRV_IDENTIFIER LIKE 'ZSB_X%') / `/IWFND/I_MED_SRV`; HTTP GET of the OData `$metadata` answers 200 | | | | |
| 200 | routeServiceBindingAction | `action="edit", target="UNPUBLISH_SERVICE", params={"service_name":"ZSB_X"}`; `service_version` | W | handleUnpublishServiceBinding | `/IWFND/I_MED_SRH` row gone; `$metadata` 404 | | | | |
| 201 | routeServiceBindingAction | `action="edit", params={"type":"publish_service","service_name":"ZSB_X"}` | W | handlePublishServiceBinding | as #199 | | | | |
| 202 | routeServiceBindingAction | `action="edit", params={"type":"unpublish_service","service_name":"ZSB_X"}` | W | handleUnpublishServiceBinding | as #200 | | | | |
| 203 | routeI18nAction | `action="i18n", params={"op":"texts","object_url":"/sap/bc/adt/oo/classes/zcl_x","language":"DE"}` | R | handleGetObjectTextsInLanguage | — | | | | |
| 204 | routeI18nAction | `action="i18n", params={"op":"data_element_labels","name":"MATNR","language":"DE"}` | R | handleGetDataElementLabels | — | | | | |
| 205 | routeI18nAction | `action="i18n", params={"op":"message_class_texts","name":"ZMSG","language":"DE"}` | R | handleGetMessageClassTexts | — | | | | |
| 206 | routeI18nAction | `action="i18n", params={"op":"text_pool","program_name":"ZREPORT","language":"DE"}` | R | handleGetTextPoolInLanguage | — | | | | |
| 207 | routeI18nAction | `action="i18n", params={"op":"compare_languages","object_url":"…","source_language":"EN","target_language":"DE"}` (the route's example says `languages`; the handler wants `source_language`/`target_language`) | R | handleCompareObjectLanguages | — | | | | |
| 208 | routeI18nAction | `action="i18n", params={"op":"write_labels","name":"ZDTEL","language":"DE","lock_handle":"…","short":"…","medium":"…","long":"…","heading":"…"}`; `transport` | W | handleWriteDataElementLabels | SQL `SELECT SCRTEXT_S,SCRTEXT_M,SCRTEXT_L,REPTEXT FROM DD04T WHERE ROLLNAME='ZDTEL' AND DDLANGUAGE='D'`; `i18n op=data_element_labels` | | | | |
| 209 | routeI18nAction | `action="i18n", params={"op":"write_message_texts","name":"ZMSG","language":"DE","lock_handle":"…","texts":{…}}`; `transport` | W | handleWriteMessageClassTexts | SQL `SELECT MSGNR,TEXT FROM T100 WHERE ARBGB='ZMSG' AND SPRSL='D'`; `i18n op=message_class_texts` | | | | |
| 210 | routeI18nAction | `action="i18n"` with unknown/missing `op` | R | needParams("i18n") guidance | — | | | | |
| 211 | routeRevisionsAction | `action="revisions", target="CLAS ZCL_X"` (op defaults to `list`; or `params={"type":"CLAS","name":"ZCL_X"}`); `include`, `parent`; `action="history"` is an alias | R | handleGetRevisions | — | | | | |
| 212 | routeRevisionsAction | `action="revisions", params={"op":"source","version_uri":"<from list>"}` | R | handleGetRevisionSource | — | | | | |
| 213 | routeRevisionsAction | `action="revisions", target="CLAS ZCL_X", params={"op":"compare","version1_uri":"…"}`; `version2_uri` (default: active), `include`, `parent` | R | handleCompareVersions | — | | | | |
| 214 | routeRevisionsAction | `action="revisions", params={"op":"bogus"}` | R | needParams("revisions") guidance | — | | | | |

## Registered but unreachable

Cross-checked against `tools_register.go` (+ `registerGetSource/WriteSource/GrepObjects/GrepPackages/ImportFromFile/ExportToFile` in `handlers_source.go`, `tools_groups.go`, `tools_focused.go`, `tools_aliases.go`). Expert mode registers **147** tools (146 + `SAP`), which matches the comment in `handlers_route_eleven.go`.

**Strictly unclaimed by any route: 0.** Every handler behind a registered tool is dispatched by at least one `route*Action` branch.

**Claimed but dead (shadowed by chain order) — 7 tools.** `routeSourceAction` sits first in the chain and answers `action="read"` for `CLAS/PROG/INTF/FUNC/FUGR/INCL/DDLS/BDEF/SRVD/MSAG/VIEW` via `handleGetSource`, so these `routeReadAction` branches can never execute through `SAP()`. Their handlers are functionally different (raw single-endpoint reads, JSON FM list, SE91 message list), so this is a real capability gap, not a duplicate:

| tool | handler | dead route branch | what SAP() gives instead |
|---|---|---|---|
| GetProgram | handleGetProgram | routeReadAction `read PROG` (#24) | GetSource PROG + dependency context (#4) |
| GetClass | handleGetClass | routeReadAction `read CLAS` (#25) | GetSource CLAS (#3) |
| GetInterface | handleGetInterface | routeReadAction `read INTF` (#26) | GetSource INTF (#5) |
| GetFunction | handleGetFunction | routeReadAction `read FUNC` (#27) | GetSource FUNC (#6) |
| GetFunctionGroup | handleGetFunctionGroup (JSON: FM list) | routeReadAction `read FUGR` (#28) | GetSource FUGR source text (#7) — the FM list is **not** reachable |
| GetInclude | handleGetInclude | routeReadAction `read INCL` (#29) | GetSource INCL (#8) |
| GetMessages | handleGetMessages (SE91 list) | routeReadAction `read MSAG` (#30) | GetSource MSAG (#12) |

**Defined, never registered, no route — 10 gCTS tools.** `registerGCTSTools` (tools_register.go:1920) is defined and called from nowhere; the handlers in `handlers_gcts.go` are dead in every mode: GctsListRepositories, GctsGetRepository, GctsCreateRepository, GctsDeleteRepository, GctsCloneRepository, GctsPull, GctsCommit, GctsListBranches, GctsSwitchBranch, GctsGetHistory.

**Aliases** (`gs`, `ws`, `es`, `so`, `gro`, `grp`, `gt`, `gtc`, `rq`, `sc`, `act`, `rut`, `atc`) are defined in `tools_aliases.go` but the registration loop is commented out — not registered, and not a capability of their own.

## Static observations (found while reading; not verdicts)

1. **Chain-order shadowing** of the seven read branches above (`routeSourceAction` before `routeReadAction`).
2. `parseTarget` upper-cases the whole target, so URI-style targets (`COVERAGE /sap/bc/adt/...` #40, `API_STATE /sap/bc/adt/...` #42) arrive as `/SAP/BC/ADT/...`. Whether ADT tolerates that is for the live run.
3. `routeReadAction` for `query`: the comment says "query TABL X", but the code only accepts `objectType == "SQL"` or empty, so `action="query", target="TABL T000"` falls to the `needParams` guidance (#46); `target="SQL T000"` is the working spelling (#45).
4. `routeUI5Action` checks `params.type` **before** looking at the action, so `ui5_*` types fire under any action (rows #118–124 list "any action").
5. `execute_abap` is reachable twice (`analyze` #66 and `system` #139), `MoveObject` twice (`edit MOVE` #74 and `debug MOVE` #100), service publish twice (target vs `params.type`), UI5 ops twice — same handlers, counted as separate branches.
6. `routeI18nAction`'s example for `compare_languages` uses `languages: "EN,DE"`, but `handleCompareObjectLanguages` requires `source_language` + `target_language` (#207).
7. `create_transport` (#134): the route selector is `params.type` ("create_transport"), which used to also be read as the transport request type — so the type could never be passed. FIXED 2026-09-08: the handler now reads `transport_type` (aliases `req_type`/`trfunction`).
8. `test` with no `object_url` (#64) declines in `routeDevToolsAction` and no later route claims it, so it ends in "No handler found".
9. `routeRFCAction` returns `handled=true` for every `action="rfc"`, including unknown ops (error listing the seven ops).

## Counts

- **Total rows:** 214
- **R (read-only):** 137
- **W (writes SAP state):** 77
- **Registered tools (expert mode):** 147 incl. `SAP` (146 real tools)
- **Registered but strictly unreachable:** 0
- **Registered but shadowed (dead branch):** 7 (GetProgram, GetClass, GetInterface, GetFunction, GetFunctionGroup, GetInclude, GetMessages)
- **Defined but never registered and unrouted:** 10 (gCTS)

Per-route row counts:

| route | rows | W |
|---|---|---|
| (pre-chain: info/help) | 2 | 0 |
| routeSourceAction | 21 | 10 |
| routeReadAction | 23 (7 shadowed) | 0 |
| routeSearchAction | 2 | 0 |
| routeGrepAction | 5 | 0 |
| routeCodeIntelAction | 10 | 1 |
| routeDevToolsAction | 5 | 3 |
| routeATCAction | 2 | 0 |
| routeCRUDAction | 12 | 10 |
| routeClassIncludeAction | 3 | 2 |
| routeWorkflowAction | 4 | 4 |
| routeFileIOAction | 3 | 2 |
| routeDebuggerAction | 8 | 7 |
| routeDebuggerLegacyAction | 6 | 4 |
| routeAMDPADTAction | 4 | 3 |
| routeAMDPAction | 7 | 5 |
| routeUI5Action | 14 | 8 |
| routeTransportAction | 8 | 4 |
| routeGitAction | 2 | 0 |
| routeReportAction | 6 | 3 |
| routeInstallAction | 5 | 4 |
| routeSystemAction | 4 | 0 |
| routeRFCAction | 7 | 1 |
| routeDumpsAction | 7 | 0 |
| routeTracesAction | 2 | 0 |
| routeSQLTraceAction | 2 | 0 |
| routeLintAction | 2 | 0 |
| routeAnalysisAction | 18 | 0 |
| routeContextAction | 4 | 0 |
| routeServiceBindingAction | 4 | 4 |
| routeI18nAction | 8 | 2 |
| routeRevisionsAction | 4 | 0 |
| **total** | **214** | **77** |

## Live findings — COE 7.52, 2026-09-08 (write sweep + author read sweep)

Method: author's read-only `vsp sweep` + our `scripts/write_sweep.py` (oracle-verified writes in
`$ZVSPTEST`/`ZVT_*`). Verdicts: OK / FAIL-honest (tool reported the failure) / LIAR (claimed
success, oracle disagreed) / SILENT (errored but a change happened).

### CRITICAL — fixed
- **create-over-existing DELETED the pre-existing object (data loss).** `create OBJECT`/`create OBJECT CLAS/OC`
  on a name that already exists: SAP returns 405 *already exists*; `reconcileFailedCreate`
  (pkg/adt/crud.go) then probes "does it exist?", sees the caller's own object, mistakes it for a
  partial create, and deletes it. Verified in isolation: class present → create-over → **class gone**.
  **Fixed:** `isAlreadyExistsError` guard skips reconcile on 405/ExceptionResourceAlreadyExists.
  Re-verified with the rebuilt binary: the object now survives. Rows #77/#77b.

### Honest failures on 7.52 (tool reported them; NOT false success)
| row | capability | status | cause |
|---|---|---|---|
| #79 | create TABL | 405 "errors in source" | DDIC table source rejected on 7.52 — needs the table-source format / `tables.v2` check |
| #86 | edit type=write_program (new) | 404 on LOCK | workflow write_program locks before the object exists → cannot create a *new* program this way |
| #147 | debug SET_TEXT_ELEMENTS | "one of …_texts required" | `text_symbols` dict not parsed — param-format mismatch (cf. `fields` wants a JSON *string*) |
| #134 | system create_transport | (was 400 "user action is not supported" — wrong endpoint) | FIXED: old→new endpoint fallback + `transport_type` wiring; workbench works on 7.5x & S/4, customizing on S/4 only |
| #92 | system rename | 400 | rename of an existing class failed (needs error-body detail; not a cascade — clone did exist) |
| #16 | edit INTF (upsert-create) | "Description is required" | interface upsert-create needs `description`; class upsert-create does not — inconsistent |
| #150 | install_dummy_test | 405 on cleanup | self-test install path is messy (errors + 405); low priority |

### From the author read sweep (read side)
- **dead:** `i18n op=message_class_texts`. **broken:** `i18n op=text_pool`, `revisions op=list`.
- timed-out (45s cap, not necessarily broken): `analyze type=callers`, `analyze type=call_graph`.
- likely true-empty: `analyze type=list_traces`, `list_sql_traces`, `sql_trace_state`, `tr_boundaries`.

### Not bugs (verified)
- **#80 clone WORKS** — target created, TADIR+SEOCLASS present, source correctly renamed. The sweep's
  first LIAR was our oracle (case-sensitive `source_has` vs upper-cased ADT source); oracle fixed.
- **LIAR count after oracle fix: 0.** On the write path the tool does not claim false success.
- Oracle/tool note: ADT free SQL (`query SQL`) is whitespace-sensitive — `X = 'Y'` works, `X='Y'` → 400.

## Transports — create/delete WORK; type depends on release (updated 2026-09-08)

The create endpoint is release-divergent (upstream issue #70). Two standard ADT resources:

- **7.50-7.52** — `POST /sap/bc/adt/cts/transports` (CL_CTS_ADT_RES_OBJ_RECORD->post).
  Body: asx `com.sap.adt.CreateCorrectionRequest` `{OPERATION:"I", DEVCLASS, REQUEST_TEXT, REF}`,
  `Accept: text/plain`; response `/com.sap.cts/object_record/<TRKORR>`. Read the class:
  `post()` **hardcodes `new_type_request = 'K'`** (workbench) and never reads `trfunction`;
  the `check_before_creation` BAdI gets the type as input-only and cannot change it. So on
  these releases **customizing (W) is not creatable via ADT at all** — SAP's design, not VSP.
- **S/4HANA 75x+** — that endpoint 400s; `POST /sap/bc/adt/cts/transportrequests`
  (CL_CTS_ADT_TM_REST_RES_CONT->post) with a `tm:root` body whose `tm:type` honours K/W.

`CreateTransportV2` now tries old → new and passes the request type to both. Net:

- **Workbench (K)** — works on 7.5x and on S/4HANA. Verified live on 7.52 (create → E070 → delete → gone).
- **Customizing (W)** — works on S/4HANA (new endpoint); on 7.5x it degrades to K (SAP hardcode).
- **Type is now expressible** through the tool via `transport_type` (aliases `req_type`/`trfunction`);
  `type` is the route selector and can't carry it (static obs #7). Handler fixed to read the distinct key.
- **delete_transport** — works via ADT on all releases (unchanged). **release** — untouched by policy.
- **Remedy for real W on 7.5x** — the FM path `TR_INSERT_REQUEST_WITH_TASKS` with `iv_type='W'`
  (a small backend helper report, e.g. reinstating ZVSP_TR_CREATE) or SE09/SE10 by hand.
  Not built yet; pending decision on whether customizing-on-old is worth the ZADT_VSP coupling.
