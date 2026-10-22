import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]


def command(arguments: list[str]) -> str:
    result = subprocess.run(arguments, cwd=ROOT, capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError(f"Runtime inspection failed: {arguments[0]}")
    return result.stdout


def source_manifest(directory: Path, suffixes: tuple[str, ...]) -> dict[str, str]:
    return {
        path.relative_to(directory).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.rglob("*"))
        if path.is_file() and path.suffix in suffixes
    }


def verify(files: list[str]) -> dict:
    compose = ["docker", "compose", "-p", "shopquery-ai"]
    for file in files:
        compose.extend(["-f", file])
    effective = json.loads(command([*compose, "config", "--format", "json"]))
    report = {
        "compose_files": files,
        "head": command(["git", "rev-parse", "HEAD"]).strip(),
        "tracked_changes": bool(command(["git", "diff", "HEAD", "--name-only"])),
        "services": {},
    }
    for service in ("api", "web", "db", "devdb"):
        container_id = (
            command([*compose, "ps", "-q", service]).strip()
            if (service in effective["services"])
            else ""
        )
        if not container_id:
            continue
        container = json.loads(command(["docker", "inspect", container_id]))[0]
        actual = dict(item.split("=", 1) for item in container["Config"]["Env"])
        expected = effective["services"][service].get("environment", {})
        drift = sorted(key for key, value in expected.items() if actual.get(key) != str(value))
        item = {
            "container": container_id,
            "image": container["Image"],
            "health": container["State"].get("Health", {}).get("Status", "none"),
            "environment_drift_names": drift,
            "mounts": [
                {
                    "source": m.get("Name", m["Source"]),
                    "target": m["Destination"],
                    "read_only": not m["RW"],
                }
                for m in container["Mounts"]
            ],
        }
        if service == "api":
            database = urlsplit(actual["DATABASE_SETUP_URL"])
            item["database"] = {"host": database.hostname, "name": database.path.lstrip("/")}
            local = source_manifest(ROOT / "backend" / "app", (".py",))
            code = (
                "import hashlib,json,pathlib; root=pathlib.Path('/app/app'); "
                "print(json.dumps({p.relative_to(root).as_posix():"
                "hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob('*.py'))}))"
            )
            remote = json.loads(command(["docker", "exec", container_id, "python", "-c", code]))
            item["source_mismatches"] = sorted(
                k for k in local.keys() | remote.keys() if local.get(k) != remote.get(k)
            )
            item["source_manifest"] = hashlib.sha256(
                json.dumps(remote, sort_keys=True).encode()
            ).hexdigest()
            item["source_modules"] = len(remote)
        report["services"][service] = item
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Read-only source and config comparison; no AI calls"
    )
    parser.add_argument("--compose-file", action="append", required=True)
    arguments = parser.parse_args()
    print(json.dumps(verify(arguments.compose_file), indent=2, ensure_ascii=False))
