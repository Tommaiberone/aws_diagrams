from diagrams import Diagram, Cluster, Edge
from diagrams.aws.network import CloudFront, Route53, APIGateway
from diagrams.aws.compute import Lambda, ECS, Fargate, ECR
from diagrams.aws.database import Aurora, ElastiCache, DDB
from diagrams.aws.integration import SQS, SNS, Eventbridge
from diagrams.aws.storage import S3
from diagrams.aws.security import Cognito, WAF, SecretsManager
from diagrams.aws.management import Cloudwatch
from diagrams.aws.devtools import Codepipeline, Codebuild
from diagrams.onprem.client import Users

with Diagram("Microservices Platform", direction="LR"):

    users = Users("Clients")

    with Cluster("Edge & Security"):
        dns = Route53("DNS")
        waf = WAF("WAF")
        cdn = CloudFront("CDN")
        auth = Cognito("User Pool")

    assets = S3("Static Assets")

    with Cluster("API Layer"):
        gw  = APIGateway("API Gateway")
        bff = Lambda("BFF Lambda")

    with Cluster("Order Service"):
        order_svc = Fargate("Orders")
        order_db  = Aurora("Postgres")
        order_q   = SQS("Orders Queue")

    with Cluster("Product Service"):
        product_svc   = Fargate("Products")
        product_cache = ElastiCache("Redis")
        product_db    = DDB("Catalog")

    with Cluster("Event Bus"):
        bus   = Eventbridge("Event Bus")
        topic = SNS("Notifications")
        notif = Lambda("Notifier")

    with Cluster("Observability"):
        logs = Cloudwatch("Logs & Metrics")

    with Cluster("CI/CD"):
        registry  = ECR("Image Registry")
        pipeline  = Codepipeline("Pipeline")
        build     = Codebuild("Build")

    secrets = SecretsManager("Secrets")

    users >> dns >> waf >> cdn
    cdn   >> Edge(label="static") >> assets
    users >> auth >> Edge(label="JWT") >> gw
    cdn   >> gw
    gw    >> bff
    bff   >> Edge(label="place order") >> order_svc
    bff   >> Edge(label="browse")      >> product_svc
    order_svc   >> order_db
    order_svc   >> Edge(label="async") >> order_q >> bus
    product_svc >> product_cache
    product_svc >> product_db
    bus   >> topic >> notif
    order_svc   >> logs
    product_svc >> logs
    build >> registry >> pipeline
    pipeline >> order_svc
    pipeline >> product_svc
    order_svc   >> secrets
    product_svc >> secrets
