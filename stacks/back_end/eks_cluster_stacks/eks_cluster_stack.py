from aws_cdk import aws_iam as _iam
from aws_cdk import aws_eks as _eks
from aws_cdk import aws_ec2 as _ec2
from aws_cdk import core as cdk
from stacks.miztiik_global_args import GlobalArgs


class EksClusterStack(cdk.Stack):
    def __init__(
        self,
        scope: cdk.Construct,
        construct_id: str,
        stack_log_level,
        vpc,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create EKS Cluster Role
        # Apparently Cluster Admin Role should be defined in the scope of the eks cluster stack stack to prevent circular dependencies!?!?
        # https://docs.aws.amazon.com/eks/latest/userguide/getting-started-console.html
        self._eks_cluster_svc_role = _iam.Role(
            self,
            "c_SvcRole",
            assumed_by=_iam.ServicePrincipal(
                "eks.amazonaws.com"),
            managed_policies=[
                _iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonEKSClusterPolicy"
                ),
                _iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonEKS_CNI_Policy"
                ),
                _iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonEKSVPCResourceController"
                )
            ]
        )

        self._eks_node_role = _iam.Role(
            self,
            "c_NodeRole",
            assumed_by=_iam.ServicePrincipal(
                "ec2.amazonaws.com"),
            managed_policies=[
                _iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonEKSWorkerNodePolicy"
                ),
                _iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonEC2ContainerRegistryReadOnly"
                ),
                _iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonEKS_CNI_Policy"
                ),
                _iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonSSMManagedInstanceCore"
                )
            ]
        )

        c_admin_role = _iam.Role(
            self,
            "c_AdminRole",
            assumed_by=_iam.CompositePrincipal(
                _iam.AccountRootPrincipal(),
                _iam.ServicePrincipal(
                    "ec2.amazonaws.com")
            )
        )
        c_admin_role.add_to_policy(
            _iam.PolicyStatement(
                effect=_iam.Effect.ALLOW,
                actions=[
                    "eks:DescribeCluster"
                ],
                resources=["*"]
            )
        )

        # Create Security Group for EKS Cluster SG
        # eks.connections.allow_to(rds_cluster, ec2.Port.tcp(3306))
        self.eks_cluster_sg = _ec2.SecurityGroup(
            self,
            "eksClusterSG",
            vpc=vpc,
            description="EKS Cluster security group",
            allow_all_outbound=True,
        )
        cdk.Tags.of(self.eks_cluster_sg).add("Name", "eks_cluster_sg")

        # https://docs.aws.amazon.com/eks/latest/userguide/sec-group-reqs.html
        self.eks_cluster_sg.add_ingress_rule(
            peer=self.eks_cluster_sg,
            connection=_ec2.Port.all_traffic(),
            description="Allow incoming within SG"
        )

        clust_name = "c_1_event_processor"

        self.eks_cluster_1 = _eks.Cluster(
            self,
            f"{clust_name}",
            cluster_name=f"{clust_name}",
            version=_eks.KubernetesVersion.V1_18,
            vpc=vpc,
            vpc_subnets=[
                _ec2.SubnetSelection(
                    subnet_type=_ec2.SubnetType.PUBLIC),
                _ec2.SubnetSelection(
                    subnet_type=_ec2.SubnetType.PRIVATE)
            ],
            default_capacity=0,
            masters_role=c_admin_role,
            role=self._eks_cluster_svc_role,
            security_group=self.eks_cluster_sg,
            endpoint_access=_eks.EndpointAccess.PUBLIC
            # endpoint_access=_eks.EndpointAccess.PUBLIC_AND_PRIVATE
        )

        # Setup OIDC Provider
        clust_oidc_provider = _eks.OpenIdConnectProvider(
            self,
            f"{clust_name}_OIDCProvider",
            url=self.eks_cluster_1.cluster_open_id_connect_issuer_url
        )

        node_grp_1 = self.eks_cluster_1.add_nodegroup_capacity(
            f"n_g_{clust_name}",
            nodegroup_name=f"{clust_name}_n_g",
            instance_types=[
                _ec2.InstanceType("t3.medium"),
                _ec2.InstanceType("t3.large"),
            ],
            disk_size=20,
            min_size=1,
            max_size=6,
            desired_size=2,
            labels={"app": "miztiik_ng",
                    "lifecycle": "on_demand",
                    "compute_provider": "ec2"
                    },
            subnets=_ec2.SubnetSelection(
                subnet_type=_ec2.SubnetType.PUBLIC),
            ami_type=_eks.NodegroupAmiType.AL2_X86_64,
            # remote_access=_eks.NodegroupRemoteAccess(ssh_key_name="eks-ssh-keypair"),
            capacity_type=_eks.CapacityType.ON_DEMAND,
            node_role=self._eks_node_role
            # bootstrap_options={"kubelet_extra_args": "--node-labels=node.kubernetes.io/lifecycle=spot,daemonset=active,app=general --eviction-hard imagefs.available<15% --feature-gates=CSINodeInfo=true,CSIDriverRegistry=true,CSIBlockVolume=true,ExpandCSIVolumes=true"}
        )

        # This code block will provision worker nodes with Fargate Profile configuration
        fargate_n_g_3 = self.eks_cluster_1.add_fargate_profile(
            "FargateEnabled",
            fargate_profile_name="miztiik_n_g_fargate",
            selectors=[
                _eks.Selector(
                    namespace="default",
                    labels={"fargate": "enabled"}
                )
            ]
        )

        self.add_cluster_admin()
        # We like to use the Kubernetes Dashboard
        self.enable_dashboard()
        self.enable_metrics_server

        # OIDC Issuer
        self.clust_oidc_issuer = clust_oidc_provider.open_id_connect_provider_issuer
        # OIDC Provider ARN
        self.clust_oidc_provider_arn = clust_oidc_provider.open_id_connect_provider_arn

        ###########################################
        ################# OUTPUTS #################
        ###########################################
        output_0 = cdk.CfnOutput(
            self,
            "AutomationFrom",
            value=f"{GlobalArgs.SOURCE_INFO}",
            description="To know more about this automation stack, check out our github page."
        )

        output_1 = cdk.CfnOutput(
            self,
            "eksClusterAdminRole",
            value=f"{c_admin_role.role_name}",
            description="EKS Cluster Admin Role"
        )

        output_2 = cdk.CfnOutput(
            self,
            "eksClusterSvcRole",
            value=f"{self._eks_cluster_svc_role.role_name}",
            description="EKS Cluster Service Role"
        )

        output_3 = cdk.CfnOutput(
            self,
            "eksClusterOIDCIssuer",
            value=f"{self.clust_oidc_issuer}",
            description="EKS Cluster OIDC Issuer"
        )
        output_4 = cdk.CfnOutput(
            self,
            "eksClusterOIDCProviderArn",
            value=f"{self.clust_oidc_provider_arn}",
            description="EKS Cluster OIDC Issuer Url"
        )

    """
    # https://github.com/adamjkeller/cdk-eks-demo/blob/f9181a1362af9a28854fd1631f965884a9b04577/eks_cluster/alb_ingress.py
    # https://github.com/kloia/aws-cdk-samples/blob/69cb2bb45aab23e08d19d5ace24915893fe92360/python/eks-simple-fargate/eks_simple_fargate/alb_ingress.py
    def add_alb_ingress_controller(self):
        # Add ALB ingress controller to EKS
        _alb_chart = eks_cluster.add_helm_chart(
            "ALBChart",
            chart="aws-load-balancer-controller",
            repository="https://aws.github.io/eks-charts",
            release="alb",
            create_namespace=False,
            namespace="kube-system",
            values=loadYamlReplaceVarLocal("../app_resources/alb-values.yaml",
                                           fields={
                                               "{{region_name}}": region,
                                               "{{cluster_name}}": eks_cluster.cluster_name,
                                               "{{vpc_id}}": eks_cluster.vpc.vpc_id
                                           }
                                           )
        )
    """

    def add_cluster_admin(self, name="eks-admin"):
        # Add admin privileges so we can sign in to the dashboard as the service account
        sa = self.eks_cluster_1.add_manifest(
            "eks-admin-sa",
            {
                "apiVersion": "v1",
                "kind": "ServiceAccount",
                "metadata": {
                    "name": name,
                    "namespace": "kube-system",
                },
            },
        )
        binding = self.eks_cluster_1.add_manifest(
            "eks-admin-rbac",
            {
                "apiVersion": "rbac.authorization.k8s.io/v1beta1",
                "kind": "ClusterRoleBinding",
                "metadata": {"name": name},
                "roleRef": {
                    "apiGroup": "rbac.authorization.k8s.io",
                    "kind": "ClusterRole",
                    "name": "cluster-admin",
                },
                "subjects": [
                    {
                        "kind": "ServiceAccount",
                        "name": name,
                        "namespace": "kube-system",
                    }
                ],
            },
        )

    # https://docs.aws.amazon.com/eks/latest/userguide/dashboard-tutorial.html

    # CleanUp from CLI
    # kubectl delete -f https://raw.githubusercontent.com/kubernetes/dashboard/master/aio/deploy/recommended.yaml
    # kubectl delete deployment kubernetes-dashboard --namespace=kube-system

    def enable_dashboard(self, namespace: str = "kubernetes-dashboard"):
        chart = self.eks_cluster_1.add_helm_chart(
            "kubernetes-dashboard",
            namespace=namespace,
            chart="kubernetes-dashboard",
            repository="https://kubernetes.github.io/dashboard/",
            values={
                # This must be set to acccess the UI via `kubectl proxy`
                "fullnameOverride": "kubernetes-dashboard",
                "extraArgs": ["--token-ttl=0"],
            },
        )

    def enable_metrics_server(self, namespace: str = "tools"):
        metrics_server = self.eks_cluster.add_helm_chart(
            "MetricsServer",
            namespace=namespace,
            chart="metrics-server",
            repository='https://charts.helm.sh/stable',

        )
