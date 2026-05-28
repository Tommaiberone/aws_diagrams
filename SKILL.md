---
name: python-diagrams
description: Use when the user asks to create, generate, or draw an architecture diagram using Python, diagrams library, or wants to export architecture as PNG. Triggers on keywords like "diagrams", "python diagram", "architecture png", "genera diagramma", "architettura python".
---

# Python Diagrams Skill

Generate architecture diagrams using the [diagrams](https://diagrams.mingrammer.com/) Python library and the
**Diagrams Editor** — a web-based visual editor with real-time code sync and PNG export.

## Prerequisites

| Dependency | Check command | Install |
|---|---|---|
| Python | `python --version` | — |
| Graphviz | `dot -V` | `choco install graphviz` / `sudo apt-get install graphviz` |
| diagrams + editor | `python -c "import diagrams"` | `pip install "diagrams[editor]"` |

If any dependency is missing, tell the user what to install before proceeding. Do not attempt to install dependencies automatically.

## Workflow

### Step 1 — Understand the architecture

Read any existing architecture documentation, markdown files, or context the user provides. Extract:
- Components (services, databases, queues, frontends, etc.)
- Data flow direction (left-to-right or top-to-bottom)
- Groupings / clusters (e.g. AWS region, VPC, microservice boundary)

### Step 2 — Choose icons

Use the correct `diagrams` node classes. Priority order:

1. **AWS services** → `diagrams.aws.*`
2. **Generic on-prem / non-AWS** → `diagrams.generic.*` or `diagrams.onprem.*`
3. **Label only** → `diagrams.generic.blank.Blank` with a descriptive label

#### Most used AWS imports

```python
from diagrams.aws.compute     import ECS, Fargate, Lambda, ECR   # ECR is in compute, NOT storage
from diagrams.aws.database    import Aurora, RDS, Dynamodb
from diagrams.aws.network     import ALB, CloudFront, Route53
from diagrams.aws.integration import SQS, SNS, Eventbridge
from diagrams.aws.storage     import S3
from diagrams.aws.devtools    import Codebuild, Codepipeline
from diagrams.aws.management  import Cloudwatch
from diagrams.aws.security    import Cognito, WAF
```

> **⚠️ Common import mistakes:**
> - `ECR` → `diagrams.aws.compute`, **not** `diagrams.aws.storage`
> - `diagrams.aws.general` does **not** exist — use `diagrams.generic.*` for non-AWS generic nodes
> - Before writing the script, validate uncertain imports with: `python -c "from diagrams.aws.X import Y; print('ok')"`

#### Most used generic/onprem imports

```python
from diagrams.onprem.client   import Users
from diagrams.onprem.compute  import Server
from diagrams.onprem.database import PostgreSQL, MySQL
from diagrams.onprem.queue    import ActiveMQ, Kafka
from diagrams.onprem.iac      import Terraform
from diagrams.generic.compute import Rack
from diagrams.generic.database import SQL
from diagrams.generic.storage  import Storage
from diagrams.generic.network  import Firewall
```

### Step 3 — Write the Python script

Default output folder: `docs/architecture/`. If the user specifies a different folder, use that instead.

Save the script as `docs/architecture/<diagram-name>.py`.

Rules:
- **No `show=`, `filename=`, or `graph_attr=`** in the `Diagram(...)` call — the editor strips these anyway and the render endpoint controls output.
- **`direction="LR"`** for pipeline/flow diagrams; **`"TB"`** for layered/tiered architectures.
- Use `Cluster` to group related components.
- Use `Edge(label="...")` to annotate connections.
- Keep node labels short — 2 lines max, `\n` for line breaks.

#### Script template

```python
from diagrams import Diagram, Cluster, Edge
# ... other imports ...

with Diagram("<Diagram Title>", direction="LR"):
    # nodes and edges here
    pass
```

### Step 4 — Start the Diagrams Editor

Start the editor in the background (no browser window) and load the generated file into it:

```bash
diagrams editor --no-browser &
```

Wait ~2 seconds for Flask to start, then import the file via the API:

```python
import json, time, urllib.request, pathlib

# Wait for the server to be ready
for _ in range(10):
    try:
        urllib.request.urlopen("http://localhost:8888/", timeout=1)
        break
    except Exception:
        time.sleep(0.5)

code = pathlib.Path("docs/architecture/<diagram-name>.py").read_text()
payload = json.dumps({"code": code}).encode()
req = urllib.request.Request(
    "http://localhost:8888/api/import",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=10) as r:
    state = json.loads(r.read())
print(f"Imported: {state['name']} — {len(state['nodes'])} nodes, {len(state['edges'])} edges")
```

The user can now open **http://localhost:8888** in their browser to:
- Review the auto-layout
- Drag nodes, rename labels, restructure clusters
- Add/remove edges

### Step 5 — Export the PNG

Export the final PNG directly via the render API (no browser interaction needed):

```python
import json, pathlib, urllib.request

code = pathlib.Path("docs/architecture/<diagram-name>.py").read_text()
payload = json.dumps({"code": code, "format": "png"}).encode()
req = urllib.request.Request(
    "http://localhost:8888/api/render",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=30) as r:
    if r.status != 200:
        raise RuntimeError(r.read().decode())
    out = pathlib.Path("docs/architecture/<diagram-name>.png")
    out.write_bytes(r.read())
    print(f"PNG saved to {out}")
```

If the user has visually edited the diagram in the browser and saved the updated `.py` (Ctrl+S), re-read that file before calling `/api/render` so the PNG reflects their edits.

#### Troubleshooting

| Error | Fix |
|---|---|
| `ModuleNotFoundError: No module named 'diagrams'` | `pip install "diagrams[editor]"` |
| `command not found: dot` / `ExecutableNotFound` | Install Graphviz: `choco install graphviz` (Win) / `sudo apt-get install graphviz` (Linux) |
| `ImportError: cannot import name 'X'` | Wrong module path — validate with `python -c "from diagrams.aws.Y import X"` |
| Port 8888 in use | Pass `--port 8889` and update the API URLs accordingly |
| Render times out | Large diagrams can take 10–20 s; increase `timeout=` in the urllib call |

### Step 6 — Report output

After successful export, tell the user:
- **PNG path**: `docs/architecture/<diagram-name>.png`
- **Script path**: `docs/architecture/<diagram-name>.py`
- **Editor URL**: `http://localhost:8888` (still running for visual edits)
- Brief summary of what the diagram shows

## File naming

Derive a kebab-case filename from the user's request:

| Request | Filename |
|---|---|
| "as-is architecture" | `as-is-architecture` |
| "target AWS architecture" | `target-architecture` |
| "CI/CD pipeline" | `cicd-pipeline` |
| "microservices overview" | `microservices-overview` |
