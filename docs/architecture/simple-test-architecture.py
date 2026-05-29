from diagrams import Diagram, Cluster, Edge
from diagrams.aws.network import CloudFront, ALB, Route53
from diagrams.aws.compute import ECS
from diagrams.aws.database import RDS
from diagrams.aws.storage import S3
from diagrams.onprem.client import Users

with Diagram("Simple Test Architecture", direction="LR"):
    users = Users("Users")
    dns = Route53("DNS")
    cdn = CloudFront("CDN")

    with Cluster("VPC"):
        lb = ALB("Load Balancer")

        with Cluster("App Layer"):
            app1 = ECS("App Server 1")
            app2 = ECS("App Server 2")

        with Cluster("Data Layer"):
            db = RDS("PostgreSQL")
            storage = S3("Static Assets")

    users >> dns >> cdn >> lb
    lb >> [app1, app2]
    app1 >> db
    app2 >> db
    app1 >> storage
    app2 >> storage
