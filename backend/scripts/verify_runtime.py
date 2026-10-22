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
            item["gpu_requests"] = container["HostConfig"].get("DeviceRequests") or []
            if actual.get("RAG_RERANKER_DEVICE", "").startswith("cuda"):
                code = (
                    "import json,torch; print(json.dumps({'torch':torch.__version__,"
                    "'cuda_build':torch.version.cuda,'available':torch.cuda.is_available(),"
                    "'device_count':torch.cuda.device_count(),'device':"
                    "torch.cuda.get_device_name(0) if torch.cuda.is_available() else None}))"
                )
                item["cuda"] = json.loads(
                    command(["docker", "exec", container_id, "python", "-c", code])
                )
                if not item["cuda"]["available"]:
                    raise RuntimeError("Configured development CUDA device is unavailable")
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
            if actual.get("RAG_RERANKER_DEVICE") == "cuda:0":
                local_entrypoint = hashlib.sha256(
                    (ROOT / "backend" / "scripts" / "gpu_api.py").read_bytes()
                ).hexdigest()
                code = (
                    "import hashlib,pathlib; print(hashlib.sha256("
                    "pathlib.Path('/app/scripts/gpu_api.py').read_bytes()).hexdigest())"
                )
                remote_entrypoint = command(
                    ["docker", "exec", container_id, "python", "-c", code]
                ).strip()
                item["gpu_entrypoint_sha256"] = remote_entrypoint
                if local_entrypoint != remote_entrypoint:
                    raise RuntimeError("GPU development entrypoint source drift")
        if service == "web" and actual.get("SHOPQUERY_DEV_CONTAINER") == "1":
            local = source_manifest(ROOT / "frontend" / "src", (".ts", ".tsx", ".css"))
            code = (
                "const fs=require('fs'),path=require('path'),crypto=require('crypto');"
                "const root='/app/src',out={};function walk(dir){"
                "for(const entry of fs.readdirSync(dir,{withFileTypes:true})){"
                "const p=path.join(dir,entry.name);if(entry.isDirectory())walk(p);"
                "if(entry.isFile()&&/\\.(ts|tsx|css)$/.test(p))"
                "out[path.relative(root,p).split(path.sep).join('/')]=''+"
                "crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');"
                "}}walk(root);console.log(JSON.stringify(out));"
            )
            remote = json.loads(command(["docker", "exec", container_id, "node", "-e", code]))
            item["source_mismatches"] = sorted(
                k for k in local.keys() | remote.keys() if local.get(k) != remote.get(k)
            )
            item["source_files"] = len(remote)
        report["services"][service] = item
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Read-only source and config comparison; no AI calls"
    )
    parser.add_argument("--compose-file", action="append", required=True)
    arguments = parser.parse_args()
    print(json.dumps(verify(arguments.compose_file), indent=2, ensure_ascii=False))
