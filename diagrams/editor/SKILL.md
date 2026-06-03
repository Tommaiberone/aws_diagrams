---
name: python-diagrams
description: Use when the user asks to create, generate, or draw an architecture diagram using Python, diagrams library, or wants to visualize an architecture as PNG. Triggers on keywords like "diagrams", "python diagram", "architecture png", "genera diagramma", "architettura python".
---

# Python Diagrams Skill

Generate architecture diagrams as Python code, then open them in the interactive visual editor.

## Prerequisites

| Dependency | Check command | Install |
|---|---|---|
| uv | `uv --version` | [docs.astral.sh/uv](https://docs.astral.sh/uv/) |

> **No other prerequisites required.** Everything runs via `uvx --from diagrams-editor` which downloads and caches the package on demand.

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

> **Do NOT run bash import validation** for anything in the reference tables below — those imports are pre-validated. Only validate with `uv run python -c "from X import Y; print('ok')"` for imports you intend to use that are NOT in the tables.

#### AWS imports

```python
from diagrams.aws.compute     import ECS, Fargate, Lambda, ECR   # ECR is in compute, NOT storage
from diagrams.aws.database    import Aurora, RDS, Dynamodb
from diagrams.aws.network     import ALB, CloudFront, Route53, TransitGateway, NATGateway, InternetGateway, VPC, PublicSubnet, PrivateSubnet, RouteTable, TGWAttach
from diagrams.aws.integration import SQS, SNS, Eventbridge
from diagrams.aws.storage     import S3
from diagrams.aws.devtools    import Codebuild, Codepipeline
from diagrams.aws.management  import Cloudwatch
from diagrams.aws.security    import Cognito, WAF
```

> **Common mistakes:**
> - `ECR` → `diagrams.aws.compute`, **not** `diagrams.aws.storage`
> - `diagrams.aws.general` exists but its icons are AWS-branded — do **not** use it for generic non-AWS nodes; use `diagrams.generic.*` instead
> - `diagrams.generic.network` contains only: `Firewall`, `Router`, `Subnet`, `Switch`, `VPN` — there is no `Internet` node; use `Router` labeled "Internet"

#### Generic / on-prem imports

```python
from diagrams.onprem.client   import Users
from diagrams.onprem.compute  import Server
from diagrams.onprem.database import PostgreSQL, MySQL
from diagrams.onprem.queue    import ActiveMQ, Kafka
from diagrams.onprem.iac      import Terraform
from diagrams.generic.compute import Rack
from diagrams.generic.database import SQL
from diagrams.generic.storage  import Storage
from diagrams.generic.network  import Firewall, Router
```

### Step 3 — Write the Python script

Default output folder: `docs/architecture/`. Use a different folder only if the user specifies one.

Save as `docs/architecture/<diagram-name>.py`.

- Use `direction="LR"` for pipeline/flow diagrams; `"TB"` for layered/tiered architectures.
- Use `Cluster` for any logical boundary (VPC, subnet, account). Nesting is supported.
- Use `Edge(label="...")` only when the relationship is not obvious from context.
- Do **not** run the script directly with Python.

```python
from diagrams import Diagram, Cluster, Edge

with Diagram("<Title>", direction="LR"):
    with Cluster("VPC"):
        with Cluster("Private Subnet"):
            db = RDS("Aurora")
        svc = Lambda("API")
    svc >> Edge(label="query") >> db
```

### Step 4 — Tell the user how to open the editor

Do **not** run any command. Instead, instruct the user to run this command in their terminal:

```bash
uvx --from diagrams-editor diagrams editor docs/architecture/<diagram-name>.py
```

Explain that this starts a local web server at **http://localhost:8888** with the diagram already loaded, where they can:
- Drag nodes to rearrange the layout
- Double-click labels to rename them
- Click **Export PNG** to download the final image

### Step 5 — Report output

Tell the user:
- **Script path**: `docs/architecture/<diagram-name>.py`
- **Command to launch the editor** (as above)
- Brief summary of what the diagram shows

---

## Troubleshooting

| Error | Fix |
|---|---|
| `ImportError: cannot import name 'X'` | Wrong module path — validate with `uv run python -c "from diagrams.X import Y; print('ok')"`. |
| `warning: VIRTUAL_ENV=... does not match ...` | Harmless — another venv is active. `uv run` ignores it. Run `unset VIRTUAL_ENV` to suppress. |
| Port 8888 already in use | Use `--port 8889` (or any free port). |

## File naming

Derive a kebab-case filename from the user's request:

| Request | Filename |
|---|---|
| "as-is architecture" | `as-is-architecture` |
| "target AWS architecture" | `target-architecture` |
| "CI/CD pipeline" | `cicd-pipeline` |
| "microservices overview" | `microservices-overview` |
