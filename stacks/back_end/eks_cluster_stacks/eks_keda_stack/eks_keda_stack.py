from aws_cdk import aws_eks as _eks
from aws_cdk import aws_iam as _iam
from aws_cdk import core as cdk
from stacks.miztiik_global_args import GlobalArgs


class EksKedaStack(cdk.Stack):
    def __init__(
        self,
        scope: cdk.Construct,
        construct_id: str,
        stack_log_level: str,
        eks_cluster,
        clust_oidc_provider_arn,
        clust_oidc_issuer,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Add your stack resources below):

        #################################
        #######                   #######
        #######   KEDA            #######
        #######                   #######
        #################################

        app_grp_01_name = "keda"
        app_grp_01_ns_name = f"{app_grp_01_name}"
        # app_grp_01_label = {"app": f"{app_grp_01_name}"}

        app_grp_01_ns_manifest = {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {
                "name": f"{app_grp_01_ns_name}",
                        # "labels": {"name": f"{app_grp_01_ns_name}"}
            }
        }

        # Create the App 01 (Namespace)
        app_grp_01_ns = _eks.KubernetesManifest(
            self,
            f"{app_grp_01_name}-ns",
            cluster=eks_cluster,
            manifest=[
                app_grp_01_ns_manifest
            ]
        )

        ############################################
        #######                              #######
        #######   K8s Keda Service Account   #######
        #######                              #######
        ############################################

        svc_accnt_name = "keda-operator"
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
        self.keda_svc_accnt_role = _iam.Role(
            self,
            "keda-svc-accnt-role",
            assumed_by=_iam.FederatedPrincipal(
                federated=f"{clust_oidc_provider_arn}",
                conditions={
                    "StringEquals": oidc_issuer_condition_str
                },
                assume_role_action="sts:AssumeRoleWithWebIdentity"
            ),
            managed_policies=[
                _iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonSQSFullAccess"
                ),
                _iam.ManagedPolicy.from_aws_managed_policy_name(
                    "CloudWatchFullAccess"
                )
            ]
        )

        keda_svc_accnt_manifest = {
            "apiVersion": "v1",
            "kind": "ServiceAccount",
            "metadata": {
                "name": f"{svc_accnt_name}",
                "namespace": f"{svc_accnt_ns}",
                "annotations": {
                    "eks.amazonaws.com/role-arn": f"{self.keda_svc_accnt_role.role_arn}"
                }
            }
        }

        keda_svc_accnt = _eks.KubernetesManifest(
            self,
            f"{svc_accnt_name}",
            cluster=eks_cluster,
            manifest=[
                keda_svc_accnt_manifest
            ]
        )

        # Make sure the namespace is available before service accounts
        keda_svc_accnt.node.add_dependency(app_grp_01_ns)

        # Ref: https://keda.sh/docs/2.3/deploy
        # install_keda = _eks.HelmChart(
        #     self,
        #     "kedaDeployment",
        #     cluster=eks_cluster,
        #     chart="keda",
        #     repository="https://kedacore.github.io/charts",
        #     namespace="keda",
        #     create_namespace=False,
        #     values={
        #     }
        # )

        ###########################################
        ################# OUTPUTS #################
        ###########################################
        output_0 = cdk.CfnOutput(
            self,
            "AutomationFrom",
            value=f"{GlobalArgs.SOURCE_INFO}",
            description="To know more about this automation stack, check out our github page.",
        )
