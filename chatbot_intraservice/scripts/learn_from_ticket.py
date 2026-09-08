# -*- coding: utf-8 -*-

"""Обучение ассистента из заявки: gap в KB → черновик статьи → (после ревью) Confluence.



  python scripts/learn_from_ticket.py 696955

  python scripts/learn_from_ticket.py 696955 --analyze-first

  python scripts/learn_from_ticket.py 696965 --force

  python scripts/learn_from_ticket.py --scan-closed --service-id 833 --limit 5

"""

from __future__ import annotations



import argparse

import json

import sys

from pathlib import Path



ROOT = Path(__file__).resolve().parents[1]

REPO = ROOT.parent

sys.path.insert(0, str(REPO))

sys.path.insert(0, str(ROOT / "src"))



import intraservice  # noqa: E402

import kb_learning  # noqa: E402

from pipeline import PipelineRun  # noqa: E402

from settings import load_settings  # noqa: E402





def _run_analyze(task_id: str) -> dict:

    import importlib.util



    script = ROOT / "scripts" / "analyze_and_comment.py"

    spec = importlib.util.spec_from_file_location("analyze_and_comment", script)

    if spec is None or spec.loader is None:

        raise RuntimeError("analyze_and_comment.py не найден")

    mod = importlib.util.module_from_spec(spec)

    spec.loader.exec_module(mod)

    return mod.run_pipeline(task_id, post=False, learn_mode="off", trigger="cli")





def process_one(

    task_id: str,

    *,

    analyze_first: bool = False,

    force: bool = False,

    require_closed: bool = False,

    resolution: str = "",

    trigger: str = "cli",

) -> dict:

    run = PipelineRun(task_id, trigger=trigger)

    task = intraservice.get_task(task_id)

    analysis = kb_learning.load_analysis(task_id)

    if analyze_first or not analysis:

        with run.step("00_analyze", "Предварительный разбор") as step:

            analysis = _run_analyze(task_id)

            step.save({"file": analysis.get("file")})



    lifetime = None

    try:

        lifetime = intraservice.get_task_lifetime(task_id)

    except Exception as exc:

        lifetime = {"error": str(exc)[:200]}



    tr = "watch_close" if require_closed else trigger

    with run.step("01_learn", "Черновик AI-KB") as step:

        result = kb_learning.learn_from_task_data(

            task,

            analysis,

            lifetime=lifetime,

            force=force,

            require_closed=require_closed,

            resolution_override=resolution,

            trigger=tr,

        )

        step.save(result)

    run.finish("completed" if result.get("ok") else "skipped", result)

    result["pipeline_run_id"] = run.run_id

    return result





def scan_closed(service_id: int | None, limit: int, analyze_first: bool) -> list[dict]:

    """Закрытые заявки: should_auto_learn + черновик."""

    import os



    import requests



    settings = load_settings()

    if not settings.get("auto_learn_kb"):

        return [{"skipped": True, "reason": "auto_learn_kb выключен"}]



    intraservice.load_env()

    base = intraservice.api_base()

    user = intraservice._user()

    password = (os.environ.get("INTRASERVICE_PASSWORD") or "").strip()

    sids = [service_id] if service_id else list(settings.get("watch_service_ids") or [833])

    params: dict = {

        "StatusIds": ",".join(str(x) for x in (settings.get("watch_closed_status_ids") or [28, 29])),

        "pagesize": str(max(limit * 3, 15)),

        "page": "1",

        "fields": "Id,Name,StatusId,ServiceId",

        "ServiceIds": ",".join(str(x) for x in sids),

    }

    resp = requests.get(

        f"{base}/task",

        params=params,

        auth=(user, password),

        headers={"Accept": "application/json"},

        timeout=45,

        verify=False,

    )

    resp.raise_for_status()

    tasks = resp.json().get("Tasks") or resp.json().get("TaskList") or []

    results: list[dict] = []

    for row in tasks:

        if not isinstance(row, dict):

            continue

        tid = str(row.get("Id") or "")

        if not tid:

            continue

        analysis = kb_learning.load_analysis(tid)

        if not analysis and not analyze_first:

            gap = kb_learning.assess_kb_gap(None)

        else:

            if analyze_first and not analysis:

                _run_analyze(tid)

                analysis = kb_learning.load_analysis(tid)

            gap = kb_learning.assess_kb_gap(analysis)

        if not gap.get("gap") and not analyze_first:

            continue

        if len([r for r in results if r.get("ok") or r.get("skipped")]) >= limit:

            break

        results.append(

            process_one(tid, analyze_first=False, require_closed=True, trigger="watch_close")

        )

    return results





def main() -> int:

    parser = argparse.ArgumentParser(description="KB learning from HelpDesk tickets")

    parser.add_argument("task_id", nargs="?", help="Номер заявки")

    parser.add_argument("--analyze-first", action="store_true", help="Сначала analyze_and_comment")

    parser.add_argument("--force", action="store_true", help="Черновик даже если KB уже была")

    parser.add_argument(

        "--require-closed",

        action="store_true",

        help="Только для закрытых заявок (28/29)",

    )

    parser.add_argument("--resolution", default="", help="Текст решения исполнителя (override)")

    parser.add_argument("--scan-closed", action="store_true", help="Пакет: закрытые без KB")

    parser.add_argument("--service-id", type=int, default=833, help="Фильтр ServiceId для scan")

    parser.add_argument("--limit", type=int, default=5)

    args = parser.parse_args()



    if not intraservice.has_credentials():

        raise SystemExit("Нет INTRASERVICE credentials")



    if args.scan_closed:

        batch = scan_closed(args.service_id, args.limit, args.analyze_first)

        out_path = ROOT / "_learn_scan.json"

        out_path.write_text(json.dumps(batch, ensure_ascii=False, indent=2), encoding="utf-8")

        print(json.dumps({"ok": True, "count": len(batch), "file": out_path.name}, ensure_ascii=False))

        for item in batch:

            if item.get("ok"):

                print(f"  + {item.get('task_id')} → {item.get('draft_path')} ({item.get('code')})")

            else:

                print(f"  - {item.get('task_id', '?')}: {item.get('reason')}")

        return 0



    if not args.task_id:

        parser.error("Укажите task_id или --scan-closed")



    result = process_one(

        args.task_id.strip(),

        analyze_first=args.analyze_first,

        force=args.force,

        require_closed=args.require_closed,

        resolution=args.resolution,

        trigger="cli",

    )

    out_path = ROOT / f"_learn_{args.task_id.strip()}.json"

    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    if hasattr(sys.stdout, "reconfigure"):

        try:

            sys.stdout.reconfigure(encoding="utf-8")

        except Exception:

            pass

    try:

        print(json.dumps(result, ensure_ascii=False, indent=2))

    except UnicodeEncodeError:

        sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8", errors="replace"))

        sys.stdout.buffer.write(b"\n")

    return 0 if result.get("ok") else 1





if __name__ == "__main__":

    raise SystemExit(main())

