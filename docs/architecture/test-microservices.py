from diagrams import Diagram, Cluster, Edge
from diagrams.aws.network import CloudFront, Route53, ALB, APIGateway
from diagrams.aws.compute import Lambda, ECS, Fargate
from diagrams.aws.database import Aurora, ElastiCache, DDB
from diagrams.aws.integration import SQS, SNS
from diagrams.aws.storage import S3
from diagrams.aws.security import Cognito, WAF
from diagrams.onprem.client import Users

with Diagram("Microservices Platform", direction="LR"):

    users = Users("Clients")

    with Cluster("Edge"):
        dns  = Route53("DNS")
        waf  = WAF("WAF")
        cdn  = CloudFront("CDN")

    with Cluster("Auth"):
        auth = Cognito("User Pool")

    with Cluster("API"):
        gw  = APIGateway("API Gateway")
        bff = Lambda("BFF")

    with Cluster("Order Service"):
        order_svc = Fargate("Orders")
        order_db  = Aurora("Postgres")
        order_q   = SQS("Queue")

    with Cluster("Product Service"):
        product_svc   = Fargate("Products")
        product_cache = ElastiCache("Redis")
        product_db    = DDB("DynamoDB")

    with Cluster("Notifications"):
        topic = SNS("Events")
        notif = Lambda("Notifier")

    assets = S3("Static Assets")

    users >> dns >> waf >> cdn
    cdn   >> gw
    cdn   >> assets
    users >> auth >> gw
    gw    >> bff
    bff   >> order_svc
    bff   >> product_svc
    order_svc   >> order_db
    order_svc   >> order_q >> topic >> notif
    product_svc >> product_cache
    product_svc >> product_db
