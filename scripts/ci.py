"""Local CI: syntax, isolated tests, DVC pipeline and quality gate."""

import json
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def git_output(*arguments):
    return subprocess.check_output(
        ["git", *arguments], cwd=ROOT, text=True
    ).strip()


def junit_counts(path):
    if not path.exists():
        return None

    root = ET.parse(path).getroot()
    suites = [
        element for element in root.iter("testsuite")
        if not element.findall("testsuite")
    ]
    counts = {
        name: sum(int(suite.get(name, "0")) for suite in suites)
        for name in ("tests", "failures", "errors", "skipped")
    }
    return {
        "total": counts["tests"],
        "passed": (
            counts["tests"] - counts["failures"]
            - counts["errors"] - counts["skipped"]
        ),
        "failed": counts["failures"],
        "errors": counts["errors"],
        "skipped": counts["skipped"],
    }


def main():
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    evidence = ROOT / "evidence/ci" / run_id
    evidence.mkdir(parents=True)
    junit_path = evidence / "junit.xml"

    report = {
        "run_id": run_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_output("rev-parse", "HEAD"),
        "git_dirty": bool(git_output("status", "--porcelain")),
        "python_version": sys.version,
        "status": "running",
        "deployment_attempted": False,
        "stages": [],
        "test_counts": None,
    }
    started = time.perf_counter()

    def run_stage(name, command):
        log_path = evidence / f"{name}.log"
        stage_started = time.perf_counter()
        print(f"\nRUNNING: {name}", flush=True)

        try:
            with log_path.open("w", encoding="utf-8") as log:
                result = subprocess.run(
                    command,
                    cwd=ROOT,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    check=False,
                )
            exit_code = result.returncode
        except OSError as error:
            log_path.write_text(str(error) + "\n", encoding="utf-8")
            exit_code = 127

        report["stages"].append({
            "name": name,
            "status": "passed" if exit_code == 0 else "failed",
            "exit_code": exit_code,
            "seconds": round(time.perf_counter() - stage_started, 3),
            "log": str(log_path.relative_to(ROOT)),
            "command": command,
        })

        print(f"{name}: {'PASSED' if exit_code == 0 else 'FAILED'}")
        print("Log:", log_path.relative_to(ROOT))

        if exit_code != 0:
            print("\nLast log lines:")
            lines = log_path.read_text(
                encoding="utf-8", errors="replace"
            ).splitlines()
            print("\n".join(lines[-30:]))
            raise RuntimeError(f"Stage failed: {name}")

    try:
        run_stage("syntax", [
            sys.executable, "-m", "compileall",
            "-q", "src", "scripts", "tests",
        ])

        run_stage("tests", [
            sys.executable, "-m", "pytest", "tests", "-q",
            f"--junitxml={junit_path}",
        ])

        run_stage("pipeline", ["dvc", "repro", "evaluate"])

        gate_path = ROOT / "reports/pipeline_evaluation.json"
        gate = json.loads(gate_path.read_text(encoding="utf-8"))

        gate_passed = (
            gate.get("gate_passed") is True
            and gate.get("test_set_used") is False
        )
        gate_log = evidence / "quality_gate.log"
        gate_log.write_text(
            json.dumps({
                "gate_passed": gate.get("gate_passed"),
                "test_set_used": gate.get("test_set_used"),
            }, indent=2) + "\n",
            encoding="utf-8",
        )
        report["stages"].append({
            "name": "quality_gate",
            "status": "passed" if gate_passed else "failed",
            "log": str(gate_log.relative_to(ROOT)),
        })

        if not gate_passed:
            raise RuntimeError("Quality gate did not pass.")

        report["status"] = "passed"

    except KeyboardInterrupt:
        report["status"] = "interrupted"
        report["error"] = "CI interrupted by operator."

    except Exception as error:
        report["status"] = "failed"
        report["error"] = str(error)

    finally:
        try:
            report["test_counts"] = junit_counts(junit_path)
        except (ET.ParseError, ValueError) as error:
            report["status"] = "failed"
            report["junit_error"] = str(error)

        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        report["seconds"] = round(time.perf_counter() - started, 3)

        serialized = json.dumps(report, indent=2) + "\n"
        (evidence / "summary.json").write_text(
            serialized, encoding="utf-8"
        )
        (ROOT / "reports/ci_latest.json").write_text(
            serialized, encoding="utf-8"
        )

    print("\nLOCAL CI:", report["status"].upper())
    print("Test counts:", json.dumps(report["test_counts"]))
    print("Evidence:", evidence.relative_to(ROOT))
    print("Deployment attempted:", report["deployment_attempted"])

    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
