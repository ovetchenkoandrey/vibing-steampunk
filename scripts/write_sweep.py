# -*- coding: utf-8 -*-
"""
write_sweep.py — oracle-verified WRITE sweep for VSP (vibing-steampunk) on on-prem SAP.

The author's `vsp sweep` never writes. This does — but only inside a sandbox — and after
every write it asks an independent ORACLE (SQL on the base tables, ADT source read) whether
the effect is real. The verdict compares what the tool CLAIMED with what SAP SHOWS:

    OK          tool said success, oracle confirms
    FAIL-honest tool said failure, oracle confirms nothing changed
    LIAR        tool said success, oracle says nothing happened   <- what we hunt
    SILENT      tool errored/timed out but oracle shows a change  (side effect without report)

Sandbox invariant: every write targets package SANDBOX_PKG and object names start with PREFIX.
The harness refuses anything else before sending it.

Usage:
    set SAP_URL / SAP_USER / SAP_PASSWORD / SAP_CLIENT (never hardcode them here)
    python scripts/write_sweep.py --dry-run          # print the plan, send nothing
    python scripts/write_sweep.py                    # full run + cleanup
    python scripts/write_sweep.py --only prog        # probes whose id contains "prog"
    python scripts/write_sweep.py --keep             # skip cleanup (inspect leftovers)
Outputs: docs/superpowers/sweeps/write-sweep-<ts>.json and .md
"""
import argparse, datetime, json, os, subprocess, sys, time

# --------------------------------------------------------------------------- config
VSP = os.environ.get("VSP_EXE", os.path.expanduser(r"~\.claude\mcp\vsp.exe"))
VSP_ARGS = ["--insecure", "--enable-transports", "--allow-transportable-edits", "--mode", "hyperfocused"]
SANDBOX_PKG = "$ZVSPTEST"
PREFIX = "ZVT_"
PROBE_TIMEOUT = 45  # seconds, same cap as the author's sweep
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(REPO, "docs", "superpowers", "sweeps")

REQUIRED_ENV = ["SAP_URL", "SAP_USER", "SAP_PASSWORD", "SAP_CLIENT"]


# --------------------------------------------------------------------------- MCP client
class VSP:
    """Minimal JSON-RPC-over-stdio client for vsp.exe in hyperfocused mode."""

    def __init__(self, dry_run: bool):
        self.dry_run = dry_run
        self.proc = None
        self._id = 0
        if dry_run:
            return
        env = dict(os.environ, SAP_INSECURE="true")
        self.proc = subprocess.Popen(
            [VSP] + VSP_ARGS, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, env=env, text=True, encoding="utf-8")
        self._rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                                 "clientInfo": {"name": "write_sweep", "version": "1.0"}})
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        self.proc.stdin.flush()

    def _rpc(self, method, params, timeout=PROBE_TIMEOUT):
        self._id += 1
        req = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params}
        self.proc.stdin.write(json.dumps(req) + "\n")
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
        """Call SAP(action, target, params). Returns (ok, text)."""
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
        content = msg["result"]["content"][0]["text"]
        return (not msg["result"].get("isError", False)), content

    def close(self):
        if self.proc:
            try:
                self.proc.stdin.close()
                self.proc.terminate()
            except Exception:
                pass


# --------------------------------------------------------------------------- oracles
class Oracle:
    """Independent checks that bypass the write handlers: raw SQL on base tables, ADT read."""

    def __init__(self, vsp: VSP):
        self.vsp = vsp

    def sql(self, query, max_rows=20):
        ok, out = self.vsp.sap("query", "SQL", {"sql_query": query, "max_rows": max_rows})
        if not ok:
            return None, out
        try:
            return json.loads(out).get("Rows", []), out
        except ValueError:
            return None, out

    def tadir(self, obj_type, name):
        rows, _ = self.sql(f"SELECT OBJ_NAME FROM TADIR WHERE OBJECT = '{obj_type}' AND OBJ_NAME = '{name}'")
        return bool(rows)

    def package_exists(self, pkg):
        rows, _ = self.sql(f"SELECT DEVCLASS FROM TDEVC WHERE DEVCLASS = '{pkg}'")
        return bool(rows)

    def program_exists(self, name):
        rows, _ = self.sql(f"SELECT NAME FROM TRDIR WHERE NAME = '{name}'")
        return bool(rows)

    def is_inactive(self, name):
        rows, _ = self.sql(f"SELECT OBJ_NAME FROM DWINACTIV WHERE OBJ_NAME = '{name}'")
        return bool(rows)

    def transport_exists(self, trkorr):
        rows, _ = self.sql(f"SELECT TRKORR FROM E070 WHERE TRKORR = '{trkorr}'")
        return bool(rows)

    def source_contains(self, target, needle):
        ok, out = self.vsp.sap("read", target)
        return ok and (needle in out)


# --------------------------------------------------------------------------- verdict
def verdict(claimed_ok: bool, oracle_ok: bool) -> str:
    if claimed_ok and oracle_ok:
        return "OK"
    if not claimed_ok and not oracle_ok:
        return "FAIL-honest"
    if claimed_ok and not oracle_ok:
        return "LIAR"
    return "SILENT"


def claimed_success(text: str) -> bool:
    """Tool-side success as the tool itself phrases it (JSON success flag or an OK-ish text)."""
    try:
        j = json.loads(text)
        if isinstance(j, dict) and "success" in j:
            return bool(j["success"])
    except ValueError:
        pass
    t = text.lower()
    return not any(k in t for k in ("failed", "error", "not found", "timeout", "does not exist"))


# --------------------------------------------------------------------------- probes
class Sweep:
    def __init__(self, vsp: VSP, args):
        self.vsp, self.args = vsp, args
        self.o = Oracle(vsp)
        self.results = []
        self.created = []  # (kind, name) for cleanup, in creation order

    def guard(self, name=None, pkg=None):
        """Sandbox invariant — refuse before sending."""
        if pkg is not None and pkg != SANDBOX_PKG and not pkg.startswith(SANDBOX_PKG):
            raise RuntimeError(f"REFUSED: package {pkg} is outside sandbox {SANDBOX_PKG}")
        if name is not None and not name.startswith(PREFIX):
            raise RuntimeError(f"REFUSED: object {name} lacks prefix {PREFIX}")

    def record(self, pid, how, claimed_ok, claimed_text, oracle_ok, note=""):
        v = "(dry-run)" if self.vsp.dry_run else verdict(claimed_ok, oracle_ok)
        self.results.append({"id": pid, "how": how, "claimed": claimed_ok, "oracle": oracle_ok,
                             "verdict": v, "note": note, "tool_said": claimed_text[:300]})
        print(f"[{v:11}] {pid:34} {note}")

    def want(self, pid):
        return (not self.args.only) or (self.args.only.lower() in pid.lower())

    # ---- package -----------------------------------------------------------
    def probe_package(self):
        pid = "devc.create"
        if not self.want(pid):
            return
        self.guard(pkg=SANDBOX_PKG)
        how = f'create DEVC {{name:"{SANDBOX_PKG}"}}'
        if self.o.package_exists(SANDBOX_PKG) and not self.vsp.dry_run:
            self.record(pid, how, True, "(pre-existing)", True, "sandbox already present")
            return
        ok, out = self.vsp.sap("create", "DEVC", {"name": SANDBOX_PKG, "description": "VSP write-sweep sandbox"})
        exists = self.o.package_exists(SANDBOX_PKG) if not self.vsp.dry_run else True
        self.record(pid, how, claimed_success(out) and ok, out, exists, "TDEVC row present?")

    # ---- program lifecycle --------------------------------------------------
    def probe_program(self):
        name = PREFIX + "SWEEP_PROG"
        self.guard(name, SANDBOX_PKG)
        src1 = f"REPORT {name.lower()}.\nDATA lv TYPE i.\nlv = 1."
        src2 = f"REPORT {name.lower()}.\nDATA lv TYPE i.\nlv = 2. \" edited-by-sweep"

        pid = "prog.create"
        if self.want(pid):
            ok, out = self.vsp.sap("create", "PROGRAM",
                                   {"program_name": name, "description": "sweep", "package_name": SANDBOX_PKG, "source": src1})
            self.created.append(("PROG", name))
            real = (self.o.program_exists(name) and self.o.tadir("PROG", name)) if not self.vsp.dry_run else True
            self.record(pid, 'create PROGRAM', ok and claimed_success(out), out, real, "TRDIR+TADIR present?")

        pid = "prog.read"
        if self.want(pid):
            ok, out = self.vsp.sap("read", f"PROG {name}")
            real = ("lv = 1" in out) if not self.vsp.dry_run else True
            self.record(pid, f'read PROG {name}', ok, out, real, "source round-trips?")

        pid = "prog.edit"
        if self.want(pid):
            ok, out = self.vsp.sap("edit", f"PROG {name}", {"source": src2})
            real = self.o.source_contains(f"PROG {name}", "edited-by-sweep") if not self.vsp.dry_run else True
            act = (not self.o.is_inactive(name)) if not self.vsp.dry_run else True
            self.record(pid, f'edit PROG {name}', ok and claimed_success(out), out, real and act,
                        "new source visible AND not in DWINACTIV?")

        pid = "prog.delete"
        if self.want(pid):
            ok, out = self.vsp.sap("delete", "OBJECT", {"object_url": f"/sap/bc/adt/programs/programs/{name.lower()}"})
            gone = (not self.o.tadir("PROG", name)) if not self.vsp.dry_run else True
            self.record(pid, 'delete OBJECT (no lock_handle)', ok and claimed_success(out), out, gone,
                        "TADIR row gone? (tool needs lock_handle — expect FAIL-honest)")

    # ---- class lifecycle ----------------------------------------------------
    def probe_class(self):
        name = PREFIX + "SWEEP_CLS"
        self.guard(name, SANDBOX_PKG)
        src = (f"CLASS {name.lower()} DEFINITION PUBLIC FINAL CREATE PUBLIC.\n  PUBLIC SECTION.\n"
               f"    METHODS ping RETURNING VALUE(rv) TYPE string.\nENDCLASS.\n\n"
               f"CLASS {name.lower()} IMPLEMENTATION.\n  METHOD ping.\n    rv = 'pong-sweep'.\n  ENDMETHOD.\nENDCLASS.")

        pid = "clas.create_shell"
        if self.want(pid):
            ok, out = self.vsp.sap("create", "OBJECT",
                                   {"object_type": "CLAS/OC", "name": name, "package_name": SANDBOX_PKG, "description": "sweep"})
            self.created.append(("CLAS", name))
            real = self.o.tadir("CLAS", name) if not self.vsp.dry_run else True
            self.record(pid, 'create OBJECT CLAS/OC', ok and claimed_success(out), out, real, "TADIR present?")

        pid = "clas.edit_source"
        if self.want(pid):
            ok, out = self.vsp.sap("edit", f"CLAS {name}", {"source": src, "package": SANDBOX_PKG})
            real = self.o.source_contains(f"CLAS {name}", "pong-sweep") if not self.vsp.dry_run else True
            act = (not self.o.is_inactive(name)) if not self.vsp.dry_run else True
            self.record(pid, f'edit CLAS {name} (package=)', ok and claimed_success(out), out, real and act,
                        "source visible AND active?")

        pid = "clas.create_over_existing"
        if self.want(pid):
            # Known suspect: create over an existing object may DELETE it during cleanup.
            before = self.o.tadir("CLAS", name) if not self.vsp.dry_run else True
            ok, out = self.vsp.sap("create", "OBJECT",
                                   {"object_type": "CLAS/OC", "name": name, "package_name": SANDBOX_PKG, "description": "sweep"})
            after = self.o.tadir("CLAS", name) if not self.vsp.dry_run else True
            self.record(pid, 'create OBJECT over existing', ok, out, before and after,
                        "object must SURVIVE a repeated create (destructive-cleanup suspect)")

    # ---- transports (create -> verify -> delete; NEVER release) -------------
    def probe_transport(self):
        pid = "transport.create"
        trkorr = None
        if self.want(pid):
            ok, out = self.vsp.sap("system", None, {"type": "create_transport", "description": "ZVT sweep (delete me)",
                                                    "package": SANDBOX_PKG})
            if not self.vsp.dry_run:
                try:
                    trkorr = json.loads(out).get("transport") or json.loads(out).get("number")
                except ValueError:
                    import re
                    m = re.search(r"\b[A-Z0-9]{3}K\d{6}\b", out)
                    trkorr = m.group(0) if m else None
            real = self.o.transport_exists(trkorr) if (trkorr and not self.vsp.dry_run) else self.vsp.dry_run
            self.record(pid, 'system create_transport', ok and claimed_success(out), out, real, f"E070 has {trkorr}?")

        pid = "transport.list_shows_new"
        if self.want(pid) and (trkorr or self.vsp.dry_run):
            ok, out = self.vsp.sap("system", None, {"type": "list_transports"})
            real = (trkorr in out) if not self.vsp.dry_run else True
            self.record(pid, 'system list_transports', ok, out, real, "new request listed?")

        pid = "transport.delete"
        if self.want(pid) and (trkorr or self.vsp.dry_run):
            ok, out = self.vsp.sap("system", None, {"type": "delete_transport", "transport": trkorr or "DRYRUN"})
            gone = (not self.o.transport_exists(trkorr)) if not self.vsp.dry_run else True
            self.record(pid, 'system delete_transport', ok and claimed_success(out), out, gone, "E070 row gone? (no release)")

    # ---- install (truthfulness suspect #1) -----------------------------------
    def probe_install(self):
        pkg = SANDBOX_PKG  # reuse sandbox; installer creates it if absent
        objs = ["ZIF_VSP_SERVICE", "ZCL_VSP_UTILS", "ZADT_CL_TADIR_MOVE", "ZCL_VSP_RFC_SERVICE",
                "ZCL_VSP_DEBUG_SERVICE", "ZCL_VSP_AMDP_SERVICE", "ZCL_VSP_REPORT_SERVICE", "ZCL_VSP_APC_HANDLER"]
        pid = "install.check_only"
        if self.want(pid):
            ok, out = self.vsp.sap("system", None, {"type": "install_zadt_vsp", "package": pkg, "check_only": True})
            self.record(pid, 'system install_zadt_vsp check_only', ok, out, ok, "read-only plan")
        pid = "install.deploy"
        if self.want(pid) and self.args.install:
            ok, out = self.vsp.sap("system", None, {"type": "install_zadt_vsp", "package": pkg})
            claimed = ok and ("Failed: 0" in out)
            present = [o for o in objs if self.o.tadir("INTF" if o.startswith("ZIF") else "CLAS", o)] if not self.vsp.dry_run else objs
            self.record(pid, 'system install_zadt_vsp (real)', claimed, out, len(present) == len(objs),
                        f"objects really present: {len(present)}/{len(objs)}")

    # ---- cleanup --------------------------------------------------------------
    def cleanup(self):
        if self.args.keep or self.vsp.dry_run:
            print("cleanup skipped" + (" (dry-run)" if self.vsp.dry_run else " (--keep)"))
            return
        print("--- cleanup (oracle-verified) ---")
        # The tool's delete needs a lock_handle it does not expose; report leftovers honestly.
        left = [f"{k} {n}" for k, n in self.created if self.o.tadir(k, n)]
        if left:
            print("LEFTOVERS (delete via ADT/SE80 or the curl lock+DELETE recipe):", ", ".join(left))
        else:
            print("sandbox clean")
        self.results.append({"id": "cleanup", "leftovers": left})

    # ---- run ------------------------------------------------------------------
    def run(self):
        for step in (self.probe_package, self.probe_program, self.probe_class,
                     self.probe_transport, self.probe_install):
            try:
                step()
            except RuntimeError as e:  # sandbox guard
                print(f"[GUARD      ] {e}")
            except Exception as e:  # one failing probe never kills the run
                print(f"[CRASH      ] {step.__name__}: {e}")
        self.cleanup()
        return self.results


# --------------------------------------------------------------------------- report
def write_report(results, dry_run):
    os.makedirs(OUT_DIR, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    base = os.path.join(OUT_DIR, f"write-sweep-{ts}{'-dryrun' if dry_run else ''}")
    with open(base + ".json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    rows = [r for r in results if "verdict" in r]
    counts = {}
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    with open(base + ".md", "w", encoding="utf-8") as f:
        f.write(f"# write sweep — {ts}{' (dry-run)' if dry_run else ''}\n\n")
        f.write("Verdicts: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) + "\n\n")
        f.write("| id | how | tool claimed | oracle | verdict | note |\n|---|---|---|---|---|---|\n")
        for r in rows:
            f.write(f"| {r['id']} | `{r['how']}` | {r['claimed']} | {r['oracle']} | **{r['verdict']}** | {r['note']} |\n")
    print(f"\nreport: {base}.md")
    return counts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print the plan, send nothing to SAP")
    ap.add_argument("--only", default="", help="run probes whose id contains this")
    ap.add_argument("--keep", action="store_true", help="skip cleanup")
    ap.add_argument("--install", action="store_true", help="also run the REAL install_zadt_vsp probe")
    args = ap.parse_args()

    if not args.dry_run:
        missing = [k for k in REQUIRED_ENV if not os.environ.get(k)]
        if missing:
            sys.exit(f"missing env: {', '.join(missing)} (never hardcode credentials in this file)")
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
