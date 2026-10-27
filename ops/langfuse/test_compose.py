"""Validate Compose offline using synthetic secrets; never pull or start services."""

import json
import os
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REQUIRED = (
    "LF_POSTGRES_PASSWORD",
    "LF_CLICKHOUSE_PASSWORD",
    "LF_REDIS_PASSWORD",
    "LF_MINIO_USER",
    "LF_MINIO_PASSWORD",
    "LF_NEXTAUTH_SECRET",
    "LF_SALT",
    "LF_ENCRYPTION_KEY",
)


def resolve(omit: str | None = None) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("LF_")}
    env.update({key: "a" * 64 for key in REQUIRED if key != omit})
    env["LF_PUBLIC_URL"] = "http://127.0.0.1:3000"
    env["LF_MEDIA_URL"] = "http://127.0.0.1:9090"
    return subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            str(ROOT / ".env.example"),
            "-f",
            str(ROOT / "compose.yaml"),
            "config",
            "--format",
            "json",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


class ComposeSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        result = resolve()
        if result.returncode:
            raise AssertionError(
                "Synthetic Compose validation failed: " + result.stderr
            )
        cls.config = json.loads(result.stdout)

    def test_project_has_exactly_six_upstream_services(self):
        self.assertEqual(self.config["name"], "shopquery-observability")
        self.assertEqual(
            set(self.config["services"]),
            {
                "langfuse-web",
                "langfuse-worker",
                "postgres",
                "clickhouse",
                "redis",
                "minio",
            },
        )

    def test_every_image_is_immutable_without_build(self):
        for service in self.config["services"].values():
            self.assertRegex(service["image"], r"@sha256:[a-f0-9]{64}$")
            self.assertNotIn("build", service)

    def test_all_services_have_healthchecks_and_app_probes_are_internal(self):
        for service in self.config["services"].values():
            self.assertIn("test", service["healthcheck"])
        for name, url in (
            (
                "langfuse-web",
                "http://langfuse-web:3000/api/public/health?failIfDatabaseUnavailable=true",
            ),
            ("langfuse-worker", "http://langfuse-worker:3030/api/health"),
        ):
            self.assertIn(url, self.config["services"][name]["healthcheck"]["test"])

    def test_only_ui_and_media_publish_on_loopback(self):
        ports = [
            (name, p["host_ip"], str(p["published"]))
            for name, s in self.config["services"].items()
            for p in s.get("ports", [])
        ]
        self.assertCountEqual(
            ports,
            [
                ("langfuse-web", "127.0.0.1", "3000"),
                ("minio", "127.0.0.1", "9090"),
            ],
        )

    def test_storage_and_network_do_not_reference_shopquery(self):
        for volume in self.config["volumes"].values():
            self.assertTrue(volume["name"].startswith("shopquery-observability_"))
            self.assertFalse(volume.get("external", False))
        for service in self.config["services"].values():
            for mount in service.get("volumes", []):
                self.assertEqual(mount["type"], "volume")
        self.assertEqual(set(self.config["networks"]), {"default", "ingestion"})
        self.assertFalse(self.config["networks"]["default"].get("external", False))
        for name, service in self.config["services"].items():
            self.assertEqual(
                "ingestion" in service["networks"], name == "langfuse-web"
            )

    def test_shared_environment_reaches_only_local_dependencies(self):
        for name in ("langfuse-web", "langfuse-worker"):
            env = self.config["services"][name]["environment"]
            self.assertIn("@postgres:5432/langfuse", env["DATABASE_URL"])
            self.assertEqual(env["REDIS_HOST"], "redis")
            self.assertEqual(env["CLICKHOUSE_URL"], "http://clickhouse:8123")
            self.assertEqual(env["TELEMETRY_ENABLED"], "false")
            self.assertEqual(
                env["LANGFUSE_S3_EVENT_UPLOAD_ENDPOINT"], "http://minio:9000"
            )
        web = self.config["services"]["langfuse-web"]["environment"]
        self.assertEqual(
            web["LANGFUSE_S3_MEDIA_UPLOAD_INTERNAL_ENDPOINT"], "http://minio:9000"
        )

    def test_all_services_have_bounded_docker_logs(self):
        for service in self.config["services"].values():
            self.assertEqual(
                service["logging"]["options"], {"max-file": "3", "max-size": "10m"}
            )

    def test_missing_each_secret_refuses_configuration(self):
        for key in REQUIRED:
            with self.subTest(key=key):
                result = resolve(omit=key)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(key, result.stderr)

    def test_template_does_not_contain_credentials(self):
        template = (ROOT / ".env.example").read_text(encoding="utf-8")
        for key in REQUIRED:
            self.assertIsNotNone(re.search(rf"^{key}=$", template, re.MULTILINE))

    def test_api_override_is_opt_in_and_never_connects_main_database(self):
        base = {
            "services": {
                name: {"image": "example.invalid/never-pulled:configuration-only"}
                for name in ("api", "web", "db")
            }
        }
        env = {k: v for k, v in os.environ.items() if not k.startswith("LANGFUSE_")}
        result = subprocess.run(
            [
                "docker", "compose", "--env-file", str(ROOT / ".env.example"),
                "-f", "-", "-f", str(ROOT / "shopquery.compose.yaml"),
                "config", "--format", "json",
            ],
            input=json.dumps(base), env=env, text=True, capture_output=True, timeout=30,
            check=True,
        )
        config = json.loads(result.stdout)
        self.assertEqual(set(config["services"]), {"api", "web", "db"})
        for name, service in config["services"].items():
            self.assertEqual("observability" in service["networks"], name == "api")
        self.assertTrue(config["networks"]["observability"]["external"])
        self.assertEqual(config["services"]["api"]["environment"]["LANGFUSE_ENABLED"], "false")
        self.assertEqual(config["services"]["api"]["environment"]["OTEL_BSP_MAX_QUEUE_SIZE"], "512")


if __name__ == "__main__":
    unittest.main()
