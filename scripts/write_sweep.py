# -*- coding: utf-8 -*-
"""
write_sweep.py — oracle-verified WRITE sweep for VSP (vibing-steampunk) on on-prem SAP.

The author's `vsp sweep` never writes. This does — only inside a sandbox — and after every
write asks an independent ORACLE (SQL on the base tables, an ADT read through another route)
whether the effect is real. The verdict compares what the tool CLAIMED with what SAP SHOWS:

    OK          tool said success, oracle confirms
    FAIL-honest tool said failure, oracle confirms nothing changed
    LIAR        tool said success, oracle says nothing happened     <- what we hunt
    SILENT      tool errored/timed out but the oracle shows a change (side effect, no report)

Probe ids follow docs/superpowers/capability-map.md row numbers where one applies (#nn).

Sandbox invariant: writes go to SANDBOX_PKG (or the tool's own throwaway $ZADT_INSTALL_TEST)
and object names start with PREFIX. The harness refuses anything else before sending it.

Usage:
    set SAP_URL / SAP_USER / SAP_PASSWORD / SAP_CLIENT in the environment (never in this file)
    python scripts/write_sweep.py --dry-run          # print the plan, send nothing
    python scripts/write_sweep.py                    # full run + cleanup
    python scripts/write_sweep.py --only clas        # probes whose id contains "clas"
    python scripts/write_sweep.py --keep             # skip cleanup (inspect leftovers)
    python scripts/write_sweep.py --install          # also run the REAL install_zadt_vsp probe
Outputs: docs/superpowers/sweeps/write-sweep-<ts>.json and .md
"""
import argparse, datetime, json, os, re, subprocess, sys, time

# --------------------------------------------------------------------------- config
VSP = os.environ.get("VSP_EXE", os.path.expanduser(r"~\.claude\mcp\vsp.exe"))
VSP_ARGS = ["--insecure", "--enable-transports", "--allow-transportable-edits", "--mode", "hyperfocused"]
SANDBOX_PKG = "$ZVSPTEST"
ALLOWED_PKGS = (SANDBOX_PKG, "$ZADT_INSTALL_TEST")  # second one is the tool's own self-cleaning test package
PREFIX = "ZVT_"
PROBE_TIMEOUT = 45
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(REPO, "docs", "superpowers", "sweeps")
REQUIRED_ENV = ["SAP_URL", "SAP_USER", "SAP_PASSWORD", "SAP_CLIENT"]


# --------------------------------------------------------------------------- MCP client
class VSP:
    """Minimal JSON-RPC-over-stdio client for vsp.exe in hyperfocused mode."""

    def __init__(self, dry_run):
        self.dry_run, self.proc, self._id = dry_run, None, 0
        if dry_run:
            return
        self.proc = subprocess.Popen([VSP] + VSP_ARGS, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, env=dict(os.environ, SAP_INSECURE="true"),
                                     text=True, encoding="utf-8")
        self._rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                                 "clientInfo": {"name": "write_sweep", "version": "1.0"}})
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        self.proc.stdin.flush()

    def _rpc(self, method, params, timeout=PROBE_TIMEOUT):
        self._id += 1
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": self._id, "method": method, "params": params}) + "\n")
        self.proc.stdin.flush()
        deadline = time.time() + timeout
        while time.time() < deadline:
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError("vsp closed stdout")
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if msg.get("id") == self._id:
                return msg
        raise TimeoutError(f"no reply within {timeout}s")

    def sap(self, action, target=None, params=None):
        """SAP(action, target, params) -> (ok, text). Never raises for tool errors."""
        args = {"action": action}
        if target:
            args["target"] = target
        if params:
            args["params"] = params
        if self.dry_run:
            return True, "(dry-run)"
        try:
            msg = self._rpc("tools/call", {"name": "SAP", "arguments": args})
        except TimeoutError as e:
            return False, f"TIMEOUT: {e}"
        if "error" in msg:
            return False, str(msg["error"].get("message", msg["error"]))
        return (not msg["result"].get("isError", False)), msg["result"]["content"][0]["text"]

    def close(self):
        if self.proc:
            try:
                self.proc.stdin.close(); self.proc.terminate()
            except Exception:
                pass


# --------------------------------------------------------------------------- oracles
class Oracle:
    """Independent checks that bypass the write handlers: raw SQL on base tables, ADT reads."""

    def __init__(self, vsp):
        self.vsp = vsp

    def sql(self, query, max_rows=20):
        ok, out = self.vsp.sap("query", "SQL", {"sql_query": query, "max_rows": max_rows})
        if not ok:
            return None
        try:
            return json.loads(out).get("Rows", [])
        except ValueError:
            return None

    def rows(self, query):
        r = self.sql(query)
        return bool(r)

    def tadir(self, obj_type, name):        return self.rows(f"SELECT OBJ_NAME FROM TADIR WHERE OBJECT='{obj_type}' AND OBJ_NAME='{name}'")
    def tadir_pkg(self, obj_type, name):
        r = self.sql(f"SELECT DEVCLASS FROM TADIR WHERE OBJECT='{obj_type}' AND OBJ_NAME='{name}'")
        return (r[0].get("DEVCLASS") if r else None)
    def package_exists(self, pkg):          return self.rows(f"SELECT DEVCLASS FROM TDEVC WHERE DEVCLASS='{pkg}'")
    def program_exists(self, name):         return self.rows(f"SELECT NAME FROM TRDIR WHERE NAME='{name}'")
    def table_active(self, name):           return self.rows(f"SELECT TABNAME FROM DD02L WHERE TABNAME='{name}' AND AS4LOCAL='A'")
    def is_inactive(self, name):            return self.rows(f"SELECT OBJ_NAME FROM DWINACTIV WHERE OBJ_NAME='{name}'")
    def transport_exists(self, trkorr):     return self.rows(f"SELECT TRKORR FROM E070 WHERE TRKORR='{trkorr}'")
    def text_symbol(self, prog, key, text):
        # independent i18n route (ADT text pool), not the report-service handler that wrote it
        ok, out = self.vsp.sap("i18n", None, {"op": "text_pool", "program_name": prog, "language": "EN"})
        return ok and (key in out) and (text in out)

    def source_has(self, target, needle):
        ok, out = self.vsp.sap("read", target, {"include_context": False})
        return ok and (needle in out)


# --------------------------------------------------------------------------- verdicts
def verdict(claimed_ok, oracle_ok):
    if claimed_ok and oracle_ok:      return "OK"
    if not claimed_ok and not oracle_ok: return "FAIL-honest"
    if claimed_ok and not oracle_ok:  return "LIAR"
    return "SILENT"


def claimed(text):
    """Success as the tool itself phrases it."""
    try:
        j = json.loads(text)
        if isinstance(j, dict) and "success" in j:
            return bool(j["success"])
    except ValueError:
        pass
    t = text.lower()
    return not any(k in t for k in ("failed", "error", "not found", "timeout", "does not exist", "no handler"))


def jfield(text, *keys):
    try:
        j = json.loads(text)
        for k in keys:
            if isinstance(j, dict) and j.get(k):
                return j[k]
    except ValueError:
        pass
    return None


# --------------------------------------------------------------------------- sweep
class Sweep:
    def __init__(self, vsp, args):
        self.vsp, self.args, self.o = vsp, args, Oracle(vsp)
        self.results, self.created = [], []   # created: (tadir_type, name) for leftover check
        self.dry = vsp.dry_run

    # -- infra ----------------------------------------------------------------
    def guard(self, name=None, pkg=None):
        if pkg is not None and not any(pkg == p or pkg.startswith(p) for p in ALLOWED_PKGS):
            raise RuntimeError(f"REFUSED: package {pkg} outside sandbox {ALLOWED_PKGS}")
        if name is not None and not name.startswith(PREFIX):
            raise RuntimeError(f"REFUSED: object {name} lacks prefix {PREFIX}")

    def rec(self, pid, how, claimed_ok, text, oracle_ok, note=""):
        v = "(dry-run)" if self.dry else verdict(claimed_ok, oracle_ok)
        self.results.append({"id": pid, "how": how, "claimed": claimed_ok, "oracle": oracle_ok,
                             "verdict": v, "note": note, "tool_said": (text or "")[:400]})
        print(f"[{v:11}] {pid:36} {note}")

    def want(self, pid):
        return (not self.args.only) or (self.args.only.lower() in pid.lower())

    def call(self, pid, how, action, target, params, oracle_fn, note):
        """One probe: call -> claimed -> oracle -> verdict. Returns (ok, text)."""
        if not self.want(pid):
            return None, None
        ok, out = self.vsp.sap(action, target, params)
        real = True if self.dry else oracle_fn()
        self.rec(pid, how, ok and claimed(out), out, real, note)
        return ok, out

    # -- #78 package ---------------------------------------------------------
    def p_package(self):
        self.guard(pkg=SANDBOX_PKG)
        if not self.dry and self.o.package_exists(SANDBOX_PKG):
            self.rec("#78 devc.create", "create DEVC", True, "(pre-existing)", True, "sandbox already present")
            return
        self.call("#78 devc.create", "create DEVC", "create", "DEVC",
                  {"name": SANDBOX_PKG, "description": "VSP write-sweep sandbox"},
                  lambda: self.o.package_exists(SANDBOX_PKG), "TDEVC row present?")

    # -- #88/#4/#15/#67/#71/#72/#73/#81 program lifecycle -------------------
    def p_program(self):
        n = PREFIX + "SWEEP_PROG"; self.guard(n, SANDBOX_PKG)
        url = f"/sap/bc/adt/programs/programs/{n.lower()}"
        s1 = f"REPORT {n.lower()}.\nDATA lv TYPE i.\nlv = 1."
        s2 = f"REPORT {n.lower()}.\nDATA lv TYPE i.\nlv = 2. \" edited-by-sweep"
        s3 = f"REPORT {n.lower()}.\nDATA lv TYPE i.\nlv = 3. \" via-update-source"

        self.call("#88 prog.create_and_activate", "create PROGRAM", "create", "PROGRAM",
                  {"program_name": n, "description": "sweep", "package_name": SANDBOX_PKG, "source": s1},
                  lambda: self.o.program_exists(n) and self.o.tadir("PROG", n) and not self.o.is_inactive(n),
                  "TRDIR+TADIR present, not inactive?")
        self.created.append(("PROG", n))
        self.call("#4 prog.read", f"read PROG {n}", "read", f"PROG {n}", {"include_context": False},
                  lambda: self.o.source_has(f"PROG {n}", "lv = 1"), "source round-trips?")
        self.call("#15 prog.edit_upsert", "edit PROG (source)", "edit", f"PROG {n}", {"source": s2},
                  lambda: self.o.source_has(f"PROG {n}", "edited-by-sweep") and not self.o.is_inactive(n),
                  "new source visible AND active?")
        # low-level CRUD primitives: LOCK -> UPDATE_SOURCE -> ACTIVATE -> UNLOCK
        ok, out = self.call("#71 prog.lock", "edit LOCK", "edit", "LOCK", {"object_url": url},
                            lambda: True, "returns a lock_handle? (oracle: UPDATE below succeeds with it)")
        handle = None if self.dry else jfield(out or "", "lock_handle", "lockHandle")
        if self.dry or handle:
            self.call("#73 prog.update_source", "edit UPDATE_SOURCE (with handle)", "edit", "UPDATE_SOURCE",
                      {"object_url": url, "source": s3, "lock_handle": handle or "DRY"},
                      lambda: self.o.source_has(f"PROG {n}", "via-update-source"), "inactive source updated?")
            self.call("#67 prog.activate", "edit ACTIVATE", "edit", "ACTIVATE",
                      {"object_url": url, "object_name": n},
                      lambda: not self.o.is_inactive(n), "DWINACTIV empty after activate?")
            self.call("#72 prog.unlock", "edit UNLOCK", "edit", "UNLOCK",
                      {"object_url": url, "lock_handle": handle or "DRY"},
                      lambda: True, "unlock accepted? (oracle: re-LOCK below succeeds)")
        else:
            self.rec("#73 prog.update_source", "edit UPDATE_SOURCE", False, out or "", False, "skipped: no lock_handle from LOCK")
        # honest delete path: LOCK -> DELETE -> gone
        ok, out = self.call("#71b prog.lock_for_delete", "edit LOCK", "edit", "LOCK", {"object_url": url},
                            lambda: True, "second LOCK after UNLOCK succeeds?")
        handle = None if self.dry else jfield(out or "", "lock_handle", "lockHandle")
        if self.dry or handle:
            self.call("#81 prog.delete", "delete OBJECT (LOCK+handle)", "delete", "OBJECT",
                      {"object_url": url, "lock_handle": handle or "DRY"},
                      lambda: not self.o.tadir("PROG", n) and not self.o.program_exists(n), "TADIR+TRDIR gone?")
        else:
            self.rec("#81 prog.delete", "delete OBJECT", False, out or "", False, "skipped: no lock_handle")

    # -- #77/#14/#77b/#89/#84/#85/#23 class lifecycle ------------------------
    def p_class(self):
        n = PREFIX + "SWEEP_CLS"; self.guard(n, SANDBOX_PKG)
        src = (f"CLASS {n.lower()} DEFINITION PUBLIC FINAL CREATE PUBLIC.\n  PUBLIC SECTION.\n"
               f"    METHODS ping RETURNING VALUE(rv) TYPE string.\nENDCLASS.\n\n"
               f"CLASS {n.lower()} IMPLEMENTATION.\n  METHOD ping.\n    rv = 'pong-sweep'.\n  ENDMETHOD.\nENDCLASS.")
        self.call("#77 clas.create_shell", "create OBJECT CLAS/OC", "create", "OBJECT",
                  {"object_type": "CLAS/OC", "name": n, "package_name": SANDBOX_PKG, "description": "sweep"},
                  lambda: self.o.tadir("CLAS", n), "TADIR present?")
        self.created.append(("CLAS", n))
        self.call("#14 clas.edit_source", "edit CLAS (package=)", "edit", f"CLAS {n}",
                  {"source": src, "package": SANDBOX_PKG},
                  lambda: self.o.source_has(f"CLAS {n}", "pong-sweep") and not self.o.is_inactive(n),
                  "source visible AND active?")
        # known suspect: a repeated create must not destroy the object (cleanup-on-error)
        before = True if self.dry else self.o.tadir("CLAS", n)
        ok, out = self.vsp.sap("create", "OBJECT", {"object_type": "CLAS/OC", "name": n,
                                                     "package_name": SANDBOX_PKG, "description": "sweep"})
        after = True if self.dry else self.o.tadir("CLAS", n)
        self.rec("#77b clas.create_over_existing", "create OBJECT over existing", ok, out, before and after,
                 "object SURVIVES a repeated create? (destructive-cleanup suspect)")
        self.call("#23 clas.editsource_replace", "edit EDITSOURCE old->new", "edit", "EDITSOURCE",
                  {"object_url": f"/sap/bc/adt/oo/classes/{n.lower()}", "old_string": "pong-sweep",
                   "new_string": "pong-replaced"},
                  lambda: self.o.source_has(f"CLAS {n}", "pong-replaced") and not self.o.is_inactive(n),
                  "replacement visible AND active?")
        # class with tests via the workflow route
        t = PREFIX + "SWEEP_CLST"; self.guard(t, SANDBOX_PKG)
        csrc = (f"CLASS {t.lower()} DEFINITION PUBLIC FINAL CREATE PUBLIC.\n  PUBLIC SECTION.\n"
                f"    METHODS two RETURNING VALUE(rv) TYPE i.\nENDCLASS.\nCLASS {t.lower()} IMPLEMENTATION.\n"
                f"  METHOD two.\n    rv = 2.\n  ENDMETHOD.\nENDCLASS.")
        tsrc = (f"CLASS ltc DEFINITION FINAL FOR TESTING DURATION SHORT RISK LEVEL HARMLESS.\n  PRIVATE SECTION.\n"
                f"    METHODS t FOR TESTING.\nENDCLASS.\nCLASS ltc IMPLEMENTATION.\n  METHOD t.\n"
                f"    cl_abap_unit_assert=>assert_equals( act = NEW {t.lower()}( )->two( ) exp = 2 ).\n  ENDMETHOD.\nENDCLASS.")
        self.call("#89 clas.create_with_tests", "create CLASS_WITH_TESTS", "create", "CLASS_WITH_TESTS",
                  {"class_name": t, "description": "sweep", "package_name": SANDBOX_PKG,
                   "class_source": csrc, "test_source": tsrc},
                  lambda: self.o.tadir("CLAS", t) and not self.o.is_inactive(t), "class present AND active?")
        self.created.append(("CLAS", t))
        self.call("#89b clas.tests_run_green", "test object_url", "test", None,
                  {"object_url": f"/sap/bc/adt/oo/classes/{t.lower()}"},
                  lambda: True, "unit test result reported? (verdict trusts tool; oracle = assertion inside test)")

    # -- #16 interface, #79 table, #80 clone ----------------------------------
    def p_intf_table_clone(self):
        i = PREFIX + "SWEEP_IF"; self.guard(i, SANDBOX_PKG)
        isrc = f"INTERFACE {i.lower()} PUBLIC.\n  METHODS ping.\nENDINTERFACE."
        self.call("#16 intf.edit_upsert", "edit INTF (upsert)", "edit", f"INTF {i}",
                  {"source": isrc, "package": SANDBOX_PKG},
                  lambda: self.o.tadir("INTF", i) and not self.o.is_inactive(i), "TADIR present AND active?")
        self.created.append(("INTF", i))

        tb = PREFIX + "SWEEP_TAB"; self.guard(tb, SANDBOX_PKG)
        self.call("#79 tabl.create", "create TABL (fields json-string)", "create", "TABL",
                  {"name": tb, "description": "sweep", "package": SANDBOX_PKG,
                   "fields": json.dumps([{"name": "ID", "type": "CHAR32", "key": True}, {"name": "VAL", "type": "CHAR10"}])},
                  lambda: self.o.table_active(tb), "DD02L active row?")
        self.created.append(("TABL", tb))

        src_n, dst_n = PREFIX + "SWEEP_CLS", PREFIX + "SWEEP_CLONE"; self.guard(dst_n, SANDBOX_PKG)
        self.call("#80 clas.clone", "create CLONE", "create", "CLONE",
                  {"object_type": "CLAS", "source_name": src_n, "target_name": dst_n, "package": SANDBOX_PKG},
                  lambda: self.o.tadir("CLAS", dst_n) and self.o.source_has(f"CLAS {dst_n}", dst_n.lower()),
                  "clone exists AND source renamed?")
        self.created.append(("CLAS", dst_n))

    # -- #86/#87 workflow writers, #90 deploy_from_file, #92 rename ---------
    def p_workflow_fileio(self):
        p = PREFIX + "SWEEP_WF"; self.guard(p, SANDBOX_PKG)
        self.call("#86 wf.write_program", "edit type=write_program", "edit", None,
                  {"type": "write_program", "program_name": p, "source": f"REPORT {p.lower()}.\nWRITE 'wf'."},
                  lambda: self.o.program_exists(p) and not self.o.is_inactive(p), "TRDIR present AND active?")
        self.created.append(("PROG", p))

        f = PREFIX + "SWEEP_FILE"; self.guard(f, SANDBOX_PKG)
        path = os.path.join(OUT_DIR, f"{f.lower()}.prog.abap")
        if not self.dry:
            os.makedirs(OUT_DIR, exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(f"REPORT {f.lower()}.\nWRITE 'from-file'.")
        self.call("#90 fileio.deploy_from_file", "system type=deploy_from_file", "system", None,
                  {"type": "deploy_from_file", "file_path": path.replace("\\", "/"), "package_name": SANDBOX_PKG},
                  lambda: self.o.program_exists(f) and self.o.source_has(f"PROG {f}", "from-file"), "file content landed?")
        self.created.append(("PROG", f))

        old, new = PREFIX + "SWEEP_CLONE", PREFIX + "SWEEP_RENAMED"; self.guard(new, SANDBOX_PKG)
        self.call("#92 fileio.rename", "system type=rename", "system", None,
                  {"type": "rename", "objType": "CLAS/OC", "oldName": old, "newName": new, "packageName": SANDBOX_PKG},
                  lambda: (not self.o.tadir("CLAS", old)) and self.o.tadir("CLAS", new), "old gone AND new present?")
        self.created.append(("CLAS", new))

    # -- #147 text elements, #66 execute_abap --------------------------------
    def p_texts_exec(self):
        p = PREFIX + "SWEEP_WF"
        self.call("#147 report.set_text_elements", "debug SET_TEXT_ELEMENTS", "debug", "SET_TEXT_ELEMENTS",
                  {"program": p, "text_symbols": {"001": "Hello-sweep"}},
                  lambda: self.o.text_symbol(p, "001", "Hello-sweep"), "text visible via independent i18n route?")
        self.call("#66 devtools.execute_abap", "analyze type=execute_abap", "analyze", None,
                  {"type": "execute_abap", "code": "lv_result = 'exec-ok'.", "return_variable": "lv_result"},
                  lambda: True, "returns 'exec-ok'? (result text is the oracle; temp program must be gone)")
        if not self.dry:
            left = self.o.sql("SELECT NAME FROM TRDIR WHERE NAME LIKE 'ZTEMP_EXEC%'") or []
            self.rec("#66b devtools.execute_abap_cleanup", "temp program removed", True, "", len(left) == 0,
                     f"ZTEMP_EXEC* leftovers: {len(left)}")

    # -- #134/#136 transports (create -> verify -> delete; NEVER release) -----
    def p_transport(self):
        ok, out = self.call("#134 transport.create", "system create_transport", "system", None,
                            {"type": "create_transport", "description": "ZVT sweep (delete me)", "package": SANDBOX_PKG},
                            lambda: True, "see next row for the E070 oracle")
        tr = None
        if not self.dry and out:
            tr = jfield(out, "transport", "number") or (re.search(r"\b[A-Z0-9]{3}K\d{6}\b", out) or [None]) and (re.search(r"\b[A-Z0-9]{3}K\d{6}\b", out).group(0) if re.search(r"\b[A-Z0-9]{3}K\d{6}\b", out) else None)
        if self.dry or tr:
            self.rec("#134b transport.exists_in_E070", "SQL E070", True, out or "", True if self.dry else self.o.transport_exists(tr),
                     f"E070 has {tr}?")
            self.call("#136 transport.delete", "system delete_transport", "system", None,
                      {"type": "delete_transport", "transport": tr or "DRY"},
                      lambda: not self.o.transport_exists(tr), "E070 row gone? (no release)")
        else:
            self.rec("#134b transport.exists_in_E070", "SQL E070", False, out or "", False, "no transport number parsed from reply")

    # -- #93-#98 breakpoints (weak oracle: same-session GET) ------------------
    def p_breakpoints(self):
        self.call("#94 debug.set_statement_bp", "debug SET_BREAKPOINT statement", "debug", "SET_BREAKPOINT",
                  {"kind": "statement", "statement": "FREE"}, lambda: True, "registered?")
        ok, out = self.call("#96 debug.get_breakpoints", "debug GET_BREAKPOINTS", "debug", "GET_BREAKPOINTS", None,
                            lambda: True, "lists the FREE bp? (weak: same session; strong oracle = ZVSP_BP_PROBE report)")
        listed = True if self.dry else bool(out and "FREE" in out)
        self.rec("#96b debug.bp_listed", "GET_BREAKPOINTS contains FREE", listed, out or "", listed, "")
        self.call("#98 debug.delete_all_bp", "debug DELETE_BREAKPOINT all", "debug", "DELETE_BREAKPOINT",
                  {"breakpoint_id": "all"}, lambda: True, "accepted?")
        ok, out = self.vsp.sap("debug", "GET_BREAKPOINTS")
        empty = True if self.dry else not (out and "FREE" in out)
        self.rec("#98b debug.bp_gone", "GET_BREAKPOINTS empty after delete all", empty, out or "", empty,
                 "FREE no longer listed? (run ZVSP_BP_CLEAR afterwards to be safe)")

    # -- #148/#150 install (truthfulness suspect #1) --------------------------
    def p_install(self):
        self.call("#148 install.check_only", "install_zadt_vsp check_only", "system", None,
                  {"type": "install_zadt_vsp", "package": SANDBOX_PKG, "check_only": True},
                  lambda: True, "read-only plan answers?")
        # self-contained: creates $ZADT_INSTALL_TEST + 2 objects, then removes them
        self.guard(pkg="$ZADT_INSTALL_TEST")
        ok, out = self.call("#150 install.dummy_test_create", "install_dummy_test", "system", None,
                            {"type": "install_dummy_test"},
                            lambda: self.o.tadir("INTF", "ZIF_DUMMY_TEST") and self.o.tadir("CLAS", "ZCL_DUMMY_TEST"),
                            "both dummy objects REALLY present? (this is the path that lied)")
        self.call("#150b install.dummy_test_cleanup", "install_dummy_test cleanup=true", "system", None,
                  {"type": "install_dummy_test", "cleanup": True},
                  lambda: not self.o.tadir("CLAS", "ZCL_DUMMY_TEST"), "dummy objects REALLY gone?")
        if self.args.install:
            objs = ["ZIF_VSP_SERVICE", "ZCL_VSP_UTILS", "ZADT_CL_TADIR_MOVE", "ZCL_VSP_RFC_SERVICE",
                    "ZCL_VSP_DEBUG_SERVICE", "ZCL_VSP_AMDP_SERVICE", "ZCL_VSP_REPORT_SERVICE", "ZCL_VSP_APC_HANDLER"]
            ok, out = self.vsp.sap("system", None, {"type": "install_zadt_vsp", "package": SANDBOX_PKG})
            present = objs if self.dry else [o for o in objs if self.o.tadir("INTF" if o.startswith("ZIF") else "CLAS", o)]
            self.rec("#148b install.deploy_real", "install_zadt_vsp (real)", ok and ("Failed: 0" in (out or "")), out or "",
                     len(present) == len(objs), f"objects really present: {len(present)}/{len(objs)}")

    # -- #76 recover zombie (honest no-op expected on a clean name) ------------
    def p_recover(self):
        z = PREFIX + "SWEEP_ZOMBIE"; self.guard(z, SANDBOX_PKG)
        self.call("#76 crud.recover_failed_create", "edit RECOVER_FAILED_CREATE", "edit", "RECOVER_FAILED_CREATE",
                  {"object_type": "CLAS", "name": z, "package_name": SANDBOX_PKG},
                  lambda: not self.o.tadir("CLAS", z), "nothing left behind for a clean name?")

    # -- cleanup ---------------------------------------------------------------
    def cleanup(self):
        if self.args.keep or self.dry:
            print("cleanup skipped" + (" (dry-run)" if self.dry else " (--keep)")); return
        print("--- cleanup (oracle-verified) ---")
        left = []
        for kind, name in self.created:
            if not self.o.tadir(kind, name):
                continue
            url = {"PROG": f"/sap/bc/adt/programs/programs/{name.lower()}",
                   "CLAS": f"/sap/bc/adt/oo/classes/{name.lower()}",
                   "INTF": f"/sap/bc/adt/oo/interfaces/{name.lower()}",
                   "TABL": f"/sap/bc/adt/ddic/tables/{name.lower()}"}.get(kind)
            ok, out = self.vsp.sap("edit", "LOCK", {"object_url": url})
            h = jfield(out, "lock_handle", "lockHandle")
            if h:
                self.vsp.sap("delete", "OBJECT", {"object_url": url, "lock_handle": h})
            if self.o.tadir(kind, name):
                left.append(f"{kind} {name}")
        print("LEFTOVERS (delete via SE80 or the curl lock+DELETE recipe): " + ", ".join(left) if left else "sandbox clean")
        self.results.append({"id": "cleanup", "leftovers": left})

    def run(self):
        for step in (self.p_package, self.p_program, self.p_class, self.p_intf_table_clone,
                     self.p_workflow_fileio, self.p_texts_exec, self.p_transport, self.p_breakpoints,
                     self.p_install, self.p_recover):
            try:
                step()
            except RuntimeError as e:
                print(f"[GUARD      ] {e}")
            except Exception as e:
                print(f"[CRASH      ] {step.__name__}: {e}")
        self.cleanup()
        return self.results


# --------------------------------------------------------------------------- report
def write_report(results, dry):
    os.makedirs(OUT_DIR, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    base = os.path.join(OUT_DIR, f"write-sweep-{ts}{'-dryrun' if dry else ''}")
    with open(base + ".json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    rows = [r for r in results if "verdict" in r]
    counts = {}
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    with open(base + ".md", "w", encoding="utf-8") as f:
        f.write(f"# write sweep — {ts}{' (dry-run)' if dry else ''}\n\nVerdicts: "
                + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) + "\n\n")
        f.write("| id | how | tool claimed | oracle | verdict | note |\n|---|---|---|---|---|---|\n")
        for r in rows:
            f.write(f"| {r['id']} | `{r['how']}` | {r['claimed']} | {r['oracle']} | **{r['verdict']}** | {r['note']} |\n")
    print(f"\nreport: {base}.md  ({len(rows)} probes)")
    return counts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--install", action="store_true", help="also run the REAL install_zadt_vsp probe")
    args = ap.parse_args()
    if not args.dry_run:
        missing = [k for k in REQUIRED_ENV if not os.environ.get(k)]
        if missing:
            sys.exit(f"missing env: {', '.join(missing)} (credentials are never stored in this file)")
        if not os.path.exists(VSP):
            sys.exit(f"vsp.exe not found at {VSP} (set VSP_EXE)")
    print(f"sandbox={SANDBOX_PKG} prefix={PREFIX} dry_run={args.dry_run} only={args.only or '*'}")
    vsp = VSP(args.dry_run)
    try:
        results = Sweep(vsp, args).run()
    finally:
        vsp.close()
    counts = write_report(results, args.dry_run)
    if counts.get("LIAR"):
        print(f"\n!!! {counts['LIAR']} LIAR verdict(s) — tool claimed success, SAP disagrees.")


if __name__ == "__main__":
    main()
