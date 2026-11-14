"""
POC 2b - A manifest for crash recovery
======================================
The same explorer, with a scratchpad AND a checkpoint at the end of every module: manifest.json holds sessionId,
phase, exploredPaths, keyFindings and nextSteps. After module 3 the driver raises SimulatedCrash: the in-memory
history is gone, as after a real crash, a network cut or an exhausted context. resume() loads the manifest, injects
it into the first prompt of a fresh session, and runs the modules in nextSteps.

    first session:  orders, payments, inventory ──X  (3 checkpoints on disk)
    resume:         manifest ──► shipping, notifications, customers

That is 6 module steps in all, against 3 lost + 6 again for a restart without a manifest.

Besides model I/O, the log shows a warning at the crash, the manifest at the crash, the steps a per-phase checkpoint
would have lost, the re-reads after resuming, and the final manifest.

Run:  python poc2_crash_resume.py     (1 run: 3 steps, the crash, 3 resumed steps = 6 query() calls)
"""

import asyncio
import json
import sys

from claude_agent_sdk import ClaudeSDKError

from common import Settings, load_settings, log, setup_logging
from explore_setup import CRASH_AFTER, MODULE_PLAN, PHASES, ExploreState, explore_module, fresh_run_dir, repo_path

RESUME_HEADER = ("Resumed from the last checkpoint of a crashed run. Don't re-read exploredPaths; continue with "
                 "nextSteps.\n")


class SimulatedCrash(Exception):
    """Stands for a crash, a network cut or an exhausted context: the in-memory history is lost (C12)."""


async def first_session(settings: Settings, state: ExploreState) -> None:
    history: list[str] = []  # lives only in memory: the crash takes it away
    for n, module in enumerate(MODULE_PLAN, 1):
        await explore_module(settings, state, history, n, module, scratchpad=True, checkpoints=True)
        if n == CRASH_AFTER:
            raise SimulatedCrash(f"the session died after module {n} ({module})")


async def resume(settings: Settings, state: ExploreState, manifest: dict) -> list[dict]:
    """The coordinator's role, played by the driver: inject the manifest and continue with its nextSteps (C11, C14)."""
    history = [RESUME_HEADER + json.dumps(manifest, indent=2, ensure_ascii=False)]
    return [await explore_module(settings, state, history, n, module, scratchpad=True, checkpoints=True)
            for n, module in enumerate(manifest["nextSteps"], CRASH_AFTER + 1)]


async def main() -> int:
    try:
        settings = load_settings()
        setup_logging("poc2_crash_resume")
    except (OSError, RuntimeError) as exc:
        print(f"Setup failed: {exc}")
        return 1

    run_dir = fresh_run_dir("crash-resume")
    manifest_path = run_dir / "manifest.json"
    state = ExploreState(run_dir)
    try:
        try:
            await first_session(settings, state)
        except SimulatedCrash as exc:
            log.warning("SimulatedCrash: %s. The history is lost; only the files in work/%s remain", exc, run_dir.name)
        if not manifest_path.is_file():
            log.error("No manifest.json: no checkpoint was saved before the crash, so the run must restart")
            return 1

        at_crash = json.loads(manifest_path.read_text(encoding="utf-8"))
        log.info("Manifest at the crash: keys %s; phase %r; %d exploredPaths; nextSteps %s", list(at_crash),
                 at_crash["phase"], len(at_crash["exploredPaths"]), at_crash["nextSteps"])  # (C11, C14)
        phase_modules = next(modules for modules in PHASES.values() if list(MODULE_PLAN)[CRASH_AFTER - 1] in modules)
        done_in_phase = sum(list(MODULE_PLAN).index(module) < CRASH_AFTER for module in phase_modules)
        log.info("Checkpoints before the crash: %d, so %d steps lost. With one checkpoint per phase, the crash "
                 "after %d of the phase's %d modules would lose %d steps", state.checkpoints,
                 CRASH_AFTER - state.checkpoints, done_in_phase, len(phase_modules), done_in_phase)  # (C13)

        resumed_state = ExploreState(run_dir, exploration_id=at_crash["sessionId"])  # a fresh session, the same id
        runs = await resume(settings, resumed_state, at_crash)
    except ClaudeSDKError as exc:  # Claude Code not found, its process crashed, ...
        log.error("SDK error: %s", exc)
        return 1

    reads = [repo_path(result["input"].get("file_path", "")) for run in runs for result in run["tool_results"]
             if result["name"] == "Read"]
    rereads = [path for path in reads if path in at_crash["exploredPaths"]]
    final = json.loads(manifest_path.read_text(encoding="utf-8"))
    log.info("Resumed with %s; Read calls on files explored before the crash: %d %s", at_crash["nextSteps"][:1],
             len(rereads), rereads)  # (C11, C14)
    log.info("Final manifest: same sessionId %s; %d exploredPaths; nextSteps %s. Module steps run: %d, against %d for "
             "a restart without a manifest", final["sessionId"] == at_crash["sessionId"], len(final["exploredPaths"]),
             final["nextSteps"], CRASH_AFTER + len(runs), CRASH_AFTER + len(MODULE_PLAN))  # (C12)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
