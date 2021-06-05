#!/usr/bin/env python3
#!/usr/bin/env python3

from aws_cdk import core as cdk

from stacks.back_end.vpc_stack import VpcStack
from stacks.back_end.s3_stack.s3_stack import S3Stack
from stacks.back_end.eks_cluster_stacks.eks_cluster_stack import EksClusterStack
from stacks.back_end.eks_cluster_stacks.eks_ssm_daemonset_stack.eks_ssm_daemonset_stack import EksSsmDaemonSetStack
from stacks.back_end.eks_cluster_stacks.eks_keda_stack.eks_keda_stack import EksKedaStack
from stacks.back_end.eks_sqs_consumer_stack.eks_sqs_consumer_stack import EksSqsConsumerStack
from stacks.back_end.eks_sqs_producer_stack.eks_sqs_producer_stack import EksSqsProducerStack

app = cdk.App()

# S3 Bucket to hold our sales events
sales_events_bkt_stack = S3Stack(
    app,
    # f"{app.node.try_get_context('project')}-sales-events-bkt-stack",
    f"sales-events-bkt-stack",
    stack_log_level="INFO",
    description="Miztiik Automation: S3 Bucket to hold our sales events"
)


# VPC Stack for hosting Secure workloads & Other resources
vpc_stack = VpcStack(
    app,
    # f"{app.node.try_get_context('project')}-vpc-stack",
    "eks-cluster-vpc-stack",
    stack_log_level="INFO",
    description="Miztiik Automation: Custom Multi-AZ VPC"
)


# EKS Cluster to process event processor
eks_cluster_stack = EksClusterStack(
    app,
    f"eks-cluster-stack",
    stack_log_level="INFO",
    vpc=vpc_stack.vpc,
    description="Miztiik Automation: EKS Cluster to process event processor"
)

# Bootstrap EKS Nodes with SSM Agents
ssm_agent_installer_daemonset = EksSsmDaemonSetStack(
    app,
    f"ssm-agent-installer-daemonset-stack",
    stack_log_level="INFO",
    eks_cluster=eks_cluster_stack.eks_cluster_1,
    description="Miztiik Automation: Bootstrap EKS Nodes with SSM Agents"
)
# Bootstrap EKS with KEDA - Kubernetes Event-driven Autoscaling
eks_keda_stack = EksKedaStack(
    app,
    f"eks-keda-stack",
    stack_log_level="INFO",
    eks_cluster=eks_cluster_stack.eks_cluster_1,
    clust_oidc_provider_arn=eks_cluster_stack.clust_oidc_provider_arn,
    clust_oidc_issuer=eks_cluster_stack.clust_oidc_issuer,
    description="Miztiik Automation: Bootstrap EKS with KEDA - Kubernetes Event-driven Autoscaling"
)

# # Produce sales event on EKS Pods and ingest to SQS queue
sales_events_producer_stack = EksSqsProducerStack(
    app,
    f"sales-events-producer-stack",
    stack_log_level="INFO",
    eks_cluster=eks_cluster_stack.eks_cluster_1,
    clust_oidc_provider_arn=eks_cluster_stack.clust_oidc_provider_arn,
    clust_oidc_issuer=eks_cluster_stack.clust_oidc_issuer,
    sales_event_bkt=sales_events_bkt_stack.data_bkt,
    description="Miztiik Automation: Produce sales event on EKS Pods and ingest to SQS queue")

# Consumer to process sales events from SQS
sales_events_consumer_stack = EksSqsConsumerStack(
    app,
    f"sales-events-consumer-stack",
    stack_log_level="INFO",
    eks_cluster=eks_cluster_stack.eks_cluster_1,
    clust_oidc_provider_arn=eks_cluster_stack.clust_oidc_provider_arn,
    clust_oidc_issuer=eks_cluster_stack.clust_oidc_issuer,
    reliable_q=sales_events_producer_stack.reliable_q,
    sales_event_bkt=sales_events_bkt_stack.data_bkt,
    description="Miztiik Automation: Consumer to process sales events from SQS")


# Stack Level Tagging
_tags_lst = app.node.try_get_context("tags")

if _tags_lst:
    for _t in _tags_lst:
        for k, v in _t.items():
            cdk.Tags.of(app).add(
                k, v, apply_to_launched_instances=True, priority=300)

app.synth()
