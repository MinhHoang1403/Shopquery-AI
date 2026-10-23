import json

import pytest

from scripts import verify_runtime


@pytest.mark.parametrize(
    "fault",
    [None, "environment", "source", "image", "unhealthy", "missing", "revision"],
)
def test_runtime_verification_rejects_actual_drift(
    monkeypatch: pytest.MonkeyPatch, fault: str | None
) -> None:
    url = "postgresql+psycopg://reader:fixture@db:5432/shopquery"
    services = {
        "api": {
            "image": "api-image",
            "environment": {"DATABASE_SETUP_URL": url},
            "depends_on": {"db": {}},
        },
        "web": {"image": "web-image"},
        "db": {"image": "db-image"},
    }

    def command(arguments: list[str]) -> str:
        if arguments[:3] == ["git", "rev-parse", "HEAD"]:
            return "a" * 40
        if arguments[0] == "git":
            return "frontend/src/App.tsx" if fault == "revision" and "HEAD" not in arguments else ""
        if arguments[:3] == ["docker", "image", "inspect"]:
            return "wrong-image" if fault == "image" else arguments[3]
        if arguments[1] == "inspect":
            service = arguments[2].removesuffix("-container")
            labels = {"org.opencontainers.image.revision": "a" * 40} if fault == "revision" else {}
            return json.dumps(
                [
                    {
                        "Image": f"{service}-image",
                        "State": {
                            "Status": "running",
                            "Health": {
                                "Status": "unhealthy" if fault == "unhealthy" else "healthy"
                            },
                        },
                        "Config": {
                            "Env": ["DATABASE_SETUP_URL=" + url]
                            + (["TEST_FLAG=wrong"] if fault == "environment" else []),
                            "Labels": labels,
                        },
                        "Mounts": [],
                        "HostConfig": {},
                    }
                ]
            )
        if arguments[1] == "exec":
            return json.dumps({"module.py": "wrong" if fault == "source" else "same"})
        if "config" in arguments:
            if fault == "environment":
                services["api"]["environment"]["TEST_FLAG"] = "expected"
            return json.dumps({"services": services})
        if "ps" in arguments:
            return (
                ""
                if fault == "missing" and arguments[-1] == "api"
                else arguments[-1] + "-container"
            )
        raise AssertionError(arguments)

    monkeypatch.setattr(verify_runtime, "command", command)
    monkeypatch.setattr(verify_runtime, "source_manifest", lambda *_: {"module.py": "same"})
    report = verify_runtime.verify(["compose.yaml"])
    assert report["ok"] is (fault is None)
    assert bool(report["failures"]) is (fault is not None)
