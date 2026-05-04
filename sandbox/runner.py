import os
import tempfile
from pathlib import Path

import docker
import docker.errors

SANDBOX_IMAGE = "ga4-sandbox"
TIMEOUT_SECONDS = 10
MEMORY_LIMIT = "256m"
CPU_QUOTA = 50000  # 0.5 CPUs (out of 100000 = 1 CPU)


def run_code(code: str) -> dict:
    """Run a Python code string in an isolated Docker container.

    Returns {"stdout": str, "stderr": str, "exit_code": int}.
    Never raises — execution errors are returned as data.
    """
    client = docker.from_env()

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(code)
        code_path = f.name

    container = None
    try:
        # Normalize path for Docker (important on Windows)
        host_path = str(Path(code_path).resolve())

        container = client.containers.create(
            SANDBOX_IMAGE,
            command=["python", "/sandbox/script.py"],
            volumes={host_path: {"bind": "/sandbox/script.py", "mode": "ro"}},
            network_disabled=True,
            mem_limit=MEMORY_LIMIT,
            cpu_quota=CPU_QUOTA,
            read_only=False,  # container fs needs to be writable for Python tmp files
        )
        container.start()

        result = container.wait(timeout=TIMEOUT_SECONDS)
        stdout = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
        stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")
        exit_code = result["StatusCode"]

        return {"stdout": stdout, "stderr": stderr, "exit_code": exit_code}

    except docker.errors.ContainerError as e:
        return {
            "stdout": e.stdout.decode("utf-8", errors="replace") if e.stdout else "",
            "stderr": str(e),
            "exit_code": e.exit_status,
        }
    except Exception as e:
        return {"stdout": "", "stderr": str(e), "exit_code": -1}
    finally:
        if container is not None:
            try:
                container.remove(force=True)
            except Exception:
                pass
        try:
            os.unlink(code_path)
        except Exception:
            pass
