from aws_cdk import aws_eks as _eks
from aws_cdk import aws_sqs as _sqs
from aws_cdk import aws_iam as _iam
from aws_cdk import core as cdk

from stacks.miztiik_global_args import GlobalArgs


class EksSqsProducerStack(cdk.Stack):
    def __init__(
        self,
        scope: cdk.Construct,
        construct_id: str,
        stack_log_level: str,
        eks_cluster,
        clust_oidc_provider_arn,
        clust_oidc_issuer,
        sales_event_bkt,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Add your stack resources below):

        self.reliable_q = _sqs.Queue(
            self,
            "reliableQueue01",
            delivery_delay=cdk.Duration.seconds(2),
            queue_name=f"reliable_message_q",
            retention_period=cdk.Duration.days(2),
            visibility_timeout=cdk.Duration.seconds(30)
        )

        ########################################
        #######                          #######
        #######   Stream Data Producer   #######
        #######                          #######
        ########################################

        app_grp_01_name = "sales-events-producer"
        app_grp_01_ns_name = f"{app_grp_01_name}-ns"
        app_grp_01_label = {"app": f"{app_grp_01_name}"}

        app_grp_01_ns_manifest = {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {
                "name": f"{app_grp_01_ns_name}",
                        "labels": {
                            "name": f"{app_grp_01_ns_name}"
                        }
            }
        }

        # Create the App 01 (Producer Namespace)
        app_grp_01_ns = _eks.KubernetesManifest(
            self,
            f"{app_grp_01_name}-ns",
            cluster=eks_cluster,
            manifest=[
                app_grp_01_ns_manifest
            ]
        )

        #######################################
        #######                         #######
        #######   K8s Service Account   #######
        #######                         #######
        #######################################

        svc_accnt_name = "events-producer-svc-accnt"
        svc_accnt_ns = app_grp_01_ns_name

        # To make resolution of LHS during runtime, pre built the string.
        oidc_issuer_condition_str = cdk.CfnJson(
            self,
            "oidc-issuer-str",
            value={
                f"{clust_oidc_issuer}:sub": f"system:serviceaccount:{svc_accnt_ns}:{svc_accnt_name}"
            },
        )

        # Svc Account Role
        self._events_producer_svc_accnt_role = _iam.Role(
            self,
            "events-producer-svc-accnt-role",
            assumed_by=_iam.FederatedPrincipal(
                federated=f"{clust_oidc_provider_arn}",
                conditions={
                    "StringEquals": oidc_issuer_condition_str
                },
                assume_role_action="sts:AssumeRoleWithWebIdentity"
            ),
            # managed_policies=[
            #     _iam.ManagedPolicy.from_aws_managed_policy_name(
            #         "AmazonSQSFullAccess"
            #     )
            # ]
        )

        # Grant Service Account Role Permissions
        sales_event_bkt.grant_read_write(self._events_producer_svc_accnt_role)
        self.reliable_q.grant_send_messages(
            self._events_producer_svc_accnt_role)

        events_producer_svc_accnt_manifest = {
            "apiVersion": "v1",
            "kind": "ServiceAccount",
            "metadata": {
                "name": f"{svc_accnt_name}",
                "namespace": f"{svc_accnt_ns}",
                "annotations": {
                    "eks.amazonaws.com/role-arn": f"{self._events_producer_svc_accnt_role.role_arn}"
                }
            }
        }

        events_producer_svc_accnt = _eks.KubernetesManifest(
            self,
            f"{svc_accnt_name}",
            cluster=eks_cluster,
            manifest=[
                events_producer_svc_accnt_manifest
            ]
        )

        # Make sure the namespace is available before service accounts
        events_producer_svc_accnt.node.add_dependency(app_grp_01_ns)

        #######################################
        #######                         #######
        #######    APP 01 DEPLOYMENT    #######
        #######                         #######
        #######################################

        app_01_producer_deployment = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": f"{app_grp_01_name}",
                "namespace": f"{app_grp_01_ns_name}"
            },
            "spec": {
                "replicas": 2,
                "selector": {"matchLabels": app_grp_01_label},
                "template": {
                    "metadata": {"labels": app_grp_01_label},
                    "spec": {
                        "serviceAccountName": f"{svc_accnt_name}",
                        "containers": [
                            {
                                "name": f"{app_grp_01_name}",
                                "image": "python:3.8.10-alpine",
                                "command": [
                                    "sh",
                                    "-c"
                                ],
                                "args": [
                                    "wget https://raw.githubusercontent.com/miztiik/scale-eks-with-keda/master/stacks/back_end/eks_sqs_producer_stack/lambda_src/stream_data_producer.py;pip3 install --user boto3;python3 stream_data_producer.py;"
                                ],
                                "env": [
                                    {
                                        "name": "STORE_EVENTS_BKT",
                                        "value": f"{sales_event_bkt.bucket_name}"
                                    },
                                    {
                                        "name": "S3_PREFIX",
                                        "value": "sales_events"
                                    },
                                    {
                                        "name": "RELIABLE_QUEUE_NAME",
                                        "value": f"{self.reliable_q.queue_name}"
                                    },
                                    {
                                        "name": "AWS_REGION",
                                        "value": f"{cdk.Aws.REGION}"
                                    },
                                    {
                                        "name": "TOT_MSGS_TO_PRODUCE",
                                        "value": "10000"
                                    },
                                    {
                                        "name": "WAIT_SECS_BETWEEN_MSGS",
                                        "value": "1"
                                    }
                                ]
                            }
                        ]
                    }
                }
            }
        }

        # apply a kubernetes manifest to the cluster
        app_01_manifest = _eks.KubernetesManifest(
            self,
            "miztSalesEventproducerSvc",
            cluster=eks_cluster,
            manifest=[
                app_01_producer_deployment,
            ]
        )

        # Make sure the namespace and service account is available before create deployments
        app_01_manifest.node.add_dependency(app_grp_01_ns)
        app_01_manifest.node.add_dependency(events_producer_svc_accnt)

        ###########################################
        ################# OUTPUTS #################
        ###########################################
        output_0 = cdk.CfnOutput(
            self,
            "AutomationFrom",
            value=f"{GlobalArgs.SOURCE_INFO}",
            description="To know more about this automation stack, check out our github page.",
        )

        output_1 = cdk.CfnOutput(
            self,
            "ReliableMessageQueue",
            value=f"https://console.aws.amazon.com/sqs/v2/home?region={cdk.Aws.REGION}#/queues",
            description="Reliable Message Queue"
        )

        output_2 = cdk.CfnOutput(
            self,
            "ReliableMessageQueueUrl",
            value=f"{self.reliable_q.queue_url}",
            description="Reliable Message Queue Url"
        )
