![diagrams logo](assets/img/diagrams.png)

# diagrams-editor

[![license](https://img.shields.io/badge/license-MIT-blue.svg)](/LICENSE)
[![pypi version](https://badge.fury.io/py/diagrams-editor.svg)](https://badge.fury.io/py/diagrams-editor)
![python version](https://img.shields.io/badge/python-%3E%3D%203.9-blue?logo=python)

Fork of [mingrammer/diagrams](https://github.com/mingrammer/diagrams) — **Diagram as Code** with an interactive web editor and headless PNG export included out of the box.

> **Note:** installs under the `diagrams` Python namespace and replaces the original `diagrams` package. Do not install both in the same virtualenv.

## Install

```bash
uv add diagrams-editor
```

That's it. The web editor, the headless PNG export, and all dependencies come in one command.

## Usage

### Open the web editor

```bash
uv run diagrams editor
```

Opens **http://localhost:8888** in your browser. Drag nodes from the palette, draw edges, group into clusters — the Python code is generated live in the sidebar.

From there you can:
- **📥 Import .py** — load an existing diagrams file for visual editing
- **💾 Save .py** — download the generated Python code (Ctrl+S)
- **⬇ Export PNG** — download a screenshot of the canvas

### Export PNG from the command line

Useful for CI pipelines and AI agents — no browser needed.

```bash
uv run diagrams export architecture.py architecture.png
```

### One-off, without adding to the project

```bash
uv run --with diagrams-editor diagrams editor
uv run --with diagrams-editor diagrams export architecture.py architecture.png
```

### Write diagrams in Python

```python
from diagrams import Diagram, Cluster, Edge
from diagrams.aws.compute import ECS, Lambda
from diagrams.aws.database import RDS
from diagrams.aws.network import ALB

with Diagram("Web Service", direction="LR"):
    with Cluster("App"):
        svc = ECS("Service")
        fn  = Lambda("Worker")
    ALB("Load Balancer") >> svc >> RDS("Database")
```

## Providers

![aws](https://img.shields.io/badge/AWS-ff9900?logo=amazon-aws)
![azure](https://img.shields.io/badge/Azure-0089d6?logo=microsoft-azure)
![gcp](https://img.shields.io/badge/GCP-4285f4?logo=google-cloud)
![kubernetes](https://img.shields.io/badge/Kubernetes-326ce5?logo=kubernetes)
![alibaba](https://img.shields.io/badge/AlibabaCloud-ff6a00?logo=alibaba-cloud)
![oracle](https://img.shields.io/badge/OracleCloud-f80000?logo=oracle)
![onprem](https://img.shields.io/badge/OnPremises-5f87bf)
![generic](https://img.shields.io/badge/Generic-5f87bf)
![saas](https://img.shields.io/badge/SaaS-5f87bf)

Full node list: [diagrams.mingrammer.com/docs/nodes/aws](https://diagrams.mingrammer.com/docs/nodes/aws)

## Examples

The `examples/` folder contains ready-to-import `.py` files:

| File | Description |
|---|---|
| `examples/web_app.py` | Three-tier web application |
| `examples/ecommerce_platform.py` | Full e-commerce platform (34 nodes, 11 clusters) |

## License

[MIT](LICENSE) — fork of [mingrammer/diagrams](https://github.com/mingrammer/diagrams), original copyright retained.
