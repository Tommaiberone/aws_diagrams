"""
Example: Three-tier web application on AWS.

Import this file in the Diagrams Editor via the "Import .py" button.
You can also run it directly to generate a PNG:

    pip install diagrams
    python examples/web_app.py
"""
from diagrams import Cluster, Diagram
from diagrams.aws.compute import EC2, ECS, Lambda
from diagrams.aws.database import ElastiCache, RDS
from diagrams.aws.network import CloudFront, ELB, Route53
from diagrams.aws.storage import S3
from diagrams.onprem.client import Users

with Diagram("Web Application Architecture", direction="LR"):

    users = Users("Users")

    with Cluster("CDN & DNS"):
        dns = Route53("Route 53")
        cdn = CloudFront("CloudFront")

    with Cluster("Load Balancing"):
        lb = ELB("Load Balancer")

    with Cluster("Application Tier"):
        web1 = EC2("Web Server 1")
        web2 = EC2("Web Server 2")
        api  = Lambda("API Handler")
        jobs = ECS("Background Jobs")

    with Cluster("Data Tier"):
        db     = RDS("PostgreSQL")
        cache  = ElastiCache("Redis Cache")
        assets = S3("Static Assets")

    users >> dns >> cdn
    cdn >> lb
    cdn >> assets

    lb >> [web1, web2]
    [web1, web2] >> api
    api >> [db, cache]
    api >> jobs
    jobs >> db
