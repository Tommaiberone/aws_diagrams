"""
Example: Real-time e-commerce platform on AWS.

Multi-tier architecture featuring:
  - Edge security with WAF, CloudFront, Route 53
  - Serverless API layer (API Gateway + Lambda BFF)
  - ECS Fargate microservices (Order, Product, Notification)
  - Event-driven integration via SQS, SNS, EventBridge
  - Multi-database data tier (Aurora, DynamoDB + DAX, ElastiCache)
  - Real-time analytics pipeline (Kinesis → Firehose → S3 → Glue → Athena)
  - Shared observability stack (CloudWatch, X-Ray)
  - Automated CI/CD (CodeCommit → CodePipeline → CodeBuild → ECR)

Import in the Diagrams Editor via "Import .py", or run directly:
    python examples/ecommerce_platform.py
"""
from diagrams import Cluster, Diagram
from diagrams.aws.analytics import Athena, Glue, Kinesis, KinesisDataFirehose
from diagrams.aws.compute import ECR, ECS, Fargate, Lambda
from diagrams.aws.database import Aurora, DAX, DDB, ElastiCache
from diagrams.aws.devtools import Codebuild, Codecommit, Codepipeline, XRay
from diagrams.aws.integration import Eventbridge, SNS, SQS
from diagrams.aws.management import Cloudwatch
from diagrams.aws.network import ALB, APIGateway, CloudFront, Route53
from diagrams.aws.security import Cognito, KMS, SecretsManager, WAF
from diagrams.aws.storage import S3
from diagrams.onprem.client import Users

with Diagram("E-Commerce Platform", direction="LR"):

    customers = Users("Customers")

    with Cluster("Edge & Security"):
        dns = Route53("Route 53")
        waf = WAF("Web ACL")
        cdn = CloudFront("CloudFront")

    with Cluster("Auth"):
        idp   = Cognito("User Pool")
        vault = SecretsManager("Secrets Manager")

    with Cluster("API Layer"):
        gw  = APIGateway("API Gateway")
        bff = Lambda("BFF Lambda")

    with Cluster("Order Service"):
        order_lb  = ALB("Internal ALB")
        order_svc = Fargate("Orders")
        order_q   = SQS("Order Queue")
        order_fn  = Lambda("Order Processor")

    with Cluster("Product Service"):
        product_lb    = ALB("Internal ALB")
        product_svc   = Fargate("Products")
        product_cache = ElastiCache("Redis")

    with Cluster("Notification Service"):
        notif = SNS("Notifications")
        email = Lambda("Email Sender")
        push  = Lambda("Push Sender")

    with Cluster("Event Bus"):
        bus = Eventbridge("EventBridge")

    with Cluster("Data Tier"):
        db  = Aurora("Aurora PostgreSQL")
        ddb = DDB("DynamoDB")
        dax = DAX("DAX")
        kms = KMS("KMS")

    with Cluster("Analytics Pipeline"):
        stream   = Kinesis("Data Streams")
        firehose = KinesisDataFirehose("Firehose")
        lake     = S3("Data Lake")
        crawler  = Glue("Glue Crawler")
        query    = Athena("Athena")

    with Cluster("Observability"):
        cw    = Cloudwatch("CloudWatch")
        xray  = XRay("X-Ray")

    with Cluster("CI/CD"):
        repo     = Codecommit("Source")
        pipeline = Codepipeline("Pipeline")
        builder  = Codebuild("Build")
        registry = ECR("Container Registry")

    # ── Traffic flow ──────────────────────────────────────────────
    customers >> dns >> waf >> cdn >> gw
    customers >> idp >> gw
    gw >> bff

    # ── BFF fans out to microservices ─────────────────────────────
    bff >> order_lb >> order_svc
    bff >> product_lb >> product_svc

    # ── Order flow: sync write + async processing ─────────────────
    order_svc >> order_q >> order_fn
    order_fn  >> db
    order_fn  >> bus

    # ── Product flow: cache-aside pattern ─────────────────────────
    product_svc >> product_cache
    product_svc >> dax >> ddb

    # ── Event-driven notifications ────────────────────────────────
    bus >> notif
    notif >> email
    notif >> push

    # ── Analytics: events → data lake → query ─────────────────────
    bus >> stream >> firehose >> lake
    lake >> crawler >> query

    # ── Secrets injected into all services ───────────────────────
    vault >> order_svc
    vault >> product_svc

    # ── Encryption at rest ────────────────────────────────────────
    kms >> db
    kms >> ddb
    kms >> lake

    # ── Observability ─────────────────────────────────────────────
    bff      >> xray
    order_fn >> xray
    order_svc >> cw
    product_svc >> cw

    # ── CI/CD → container deployment ─────────────────────────────
    repo >> pipeline >> builder >> registry
    registry >> order_svc
    registry >> product_svc
