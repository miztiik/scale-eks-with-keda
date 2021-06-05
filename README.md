# Event Processor on Kubernetes(EKS)

The developer at Mystique Unicorn are interested in building their application using event-driven architectural pattern to process streaming data. For those who are unfamiliar, _An event-driven architecture uses events to trigger and communicate between decoupled services and is common in modern applications built with microservices. An event is a change in state, or an update, like an item being placed in a shopping cart on an e-commerce website._

In this application, they will have their physical stores, send a stream _sales_ and _inventory_ related events to a central location, where multiple downstream systems will consume these events. For example, An event for a new order will be consumed by the warehouse system and the sales events will be used by the marketing department to generate revenue and forecast reports. This pattern of separating the produce, router and consumer to independent components allows them to scale the applications without constraints.

They heard that AWS offers capabilities to build event-driven architectures using kubernetes, Can you help them?

## 🎯 Solutions

![Miztiik Automation: Event Processor On EKS Architecture](images/miztiik_automation_event_processor_on_eks_architecture_0.png)
Amazon EKS<sup>[1]</sup> gives you the flexibility to start, run, and scale Kubernetes applications in the AWS. For this demo, we will build a EKS cluster with a managed node groups running `2` _t2.medium_ nodes. We will also have a _producer_ deployment writing messages to a SQS queue. The _producer_ will produce a stream of `sales` or `inventory` events. A sample event is shown below. A _consumer_ running as deployment will process those messages and store them on S3.

```json
{
  "request_id": "a11012c7-e518-4619-9fba-4591156f5d64",
  "store_id": 7,
  "cust_id": 605,
  "category": "Shoes",
  "sku": 96290,
  "price": 87.86,
  "qty": 17,
  "discount": 17.6,
  "gift_wrap": false,
  "variant": "red",
  "priority_shipping": true,
  "ts": "2021-05-14T22:27:03.530997",
  "contact_me": "github.com/miztiik"
}
```

![Miztiik Automation: Event Processor On EKS Architecture](images/miztiik_automation_event_processor_on_eks_architecture_000.png)

In this demo, we will create a the architecture like the one shown above. We will have a

- **EKS Cluster** - Our primary cluster router with `2` managed node groups.
- **SQS Queue** - A standard SQS queue with a visibility timeout of `30`seconds, This allows our consumer `30` seconds to successfully process message and delete them from the queue.
- **Sales Events Bucket** - Persistent storage for the consumer to store the events.
- **producer** - A deployment running an generic container `python:3.8.10-alpine`. The producer code is pulled from this github directly. It will produce `1` message every `2` seconds and runs to produce a maximum of `10000` messages. Being a _deployment_, it will be restarted and goes on to produce the next batch of _10000_ messages.
- **consumer** - A deployment running generic container `python:3.8.10-alpine`. The consumer code is pulled from this github directly. Every `10` seconds it will process messages in batches of `5`. The incoming messages will be stored persistently in _Sales Events Bucket_. It will process a maximum of `10000` messages.

1.  ## 🧰 Prerequisites

    This demo, instructions, scripts and cloudformation template is designed to be run in `us-east-1`. With few modifications you can try it out in other regions as well(_Not covered here_).

    - 🛠 AWS CLI Installed & Configured - [Get help here](https://youtu.be/TPyyfmQte0U)
    - 🛠 AWS CDK Installed & Configured - [Get help here](https://www.youtube.com/watch?v=MKwxpszw0Rc)
    - 🛠 Python Packages, _Change the below commands to suit your OS, the following is written for amzn linux 2_
      - Python3 - `yum install -y python3`
      - Python Pip - `yum install -y python-pip`
      - Virtualenv - `pip3 install virtualenv`

1.  ## ⚙️ Setting up the environment

    - Get the application code

      ```bash
      git clone https://github.com/miztiik/event-processor-on-eks
      cd event-processor-on-eks
      ```

1.  ## 🚀 Prepare the dev environment to run AWS CDK

    We will use `cdk` to make our deployments easier. Lets go ahead and install the necessary components.

    ```bash
    # You should have npm pre-installed
    # If you DONT have cdk installed
    npm install -g aws-cdk

    # Make sure you in root directory
    python3 -m venv .venv
    source .venv/bin/activate
    pip3 install -r requirements.txt
    ```

    The very first time you deploy an AWS CDK app into an environment _(account/region)_, you’ll need to install a `bootstrap stack`, Otherwise just go ahead and deploy using `cdk deploy`.

    ```bash
    cdk bootstrap
    cdk ls
    # Follow on screen prompts
    ```

    You should see an output of the available stacks,

    ```bash
    eks-cluster-vpc-stack
    eks-cluster-stack
    sales-events-bkt-stack
    sales-events-producer-stack
    sales-events-consumer-stack
    ```

1.  ## 🚀 Deploying the application

    Let us walk through each of the stacks,

    - **Stack: eks-cluster-vpc-stack**
      To host our EKS cluster we need a custom VPC. This stack will build a multi-az VPC with the following attributes,

      - **VPC**:
        - 2-AZ Subnets with Public, Private and Isolated Subnets.
        - 1 NAT GW for internet access from private subnets

      Initiate the deployment with the following command,

      ```bash
      cdk deploy eks-cluster-vpc-stack
      ```

      After successfully deploying the stack, Check the `Outputs` section of the stack.

    - **Stack: eks-cluster-stack**
      As we are starting out a new cluster, we will use most default. No logging is configured or any add-ons. The cluster will have the following attributes,

      - The control pane is launched with public access. _i.e_ the cluster can be access without a bastion host
      - `c_admin` IAM role added to _aws-auth_ configMap to administer the cluster from CLI.
      - One managed EC2 node group - Launch template Two `t3.medium` instances running Amazon Linux 2 - Auto-scaling Group with `2` desired instances.
        In this demo, let us launch a EKS[1] cluster in a custom VPC using AWS CDK.
      - The EC2 Node IAM Role has been bootstrapped to access SQS & S3 with _very permissive permissions_.
      - <sup><sub>TODO: Move IAM Role creation to a separate stack. This would allows to manage permissions outside of the EKS Cluster stack.</sub><sup>

      ```bash
      cdk deploy eks-cluster-stack
      ```

      After successfully deploying the stack, Check the `Outputs` section of the stack. You will find the `*ConfigCommand*` that allows yous to interact with your cluster using `kubectl`

    - **Stack: sales-events-bkt-stack**

      This stack will create the s3 bucket. We will add a bucket policy to delegate all access management to be done by access points. _Although not required for this demo, we may use it in the future_.

      Initiate the deployment with the following command,

      ```bash
      cdk deploy sales-events-bkt-stack
      ```

      After successfully deploying the stack, Check the `Outputs` section of the stack. You will find the `SalesEventsBucket`.

    - **Stack: sales-events-producer-stack**

      We need an SQS queue for our producer to ingest message, So we will start by creating an SQS queue with the following attributes.

      - **Source Queue**: `reliable_q` - Producers will send their messages to this queue.
      - Any new message will be hidden(`DelaySeconds`) for `2` seconds
      - New message will be hidden<sup>[2]</sup>(`DelaySeconds`) for `2` seconds
      - To ensure messages are given enough time to be processed by the consumer, the visibility timeout is set to `30` seconds.
      - No Dead-Letter-Queue(DLQ) is set, _If you are interested in knowing more about DLQ, check out this demo[3]_.

      Now that we have the queue, lets discuss the producer.

      - **Namespace**: `sales-events-producer-ns` - We start by creating a new namespace. As this will be the usual case, where producers will be residing in their own namespace.
      - **Deployment**: `sales-events-producer` - This stack will create a kubernetes deployment within that namespace with `1` replica running the vanilla container `python:3.8.10-alpine`. The producer code is pulled using `wget <URL>` from the container `CMD`. If you are interested take a look at the producer code here `stacks/back_end/eks_sqs_producer_stack/lambda_src/stream_data_producer.py`. At this moment you have two customization possible. They are all populated with defaults, They can be modified using pod environment variables

        - `TOT_MSGS_TO_PRODUCE`- Use this to define the maximum number of messages you want to produce per pod lifecycle. If you want to produce a maximum of `1000`. As the pod exits successfully upon generating the maximum messages. Kubernetes will restart the pod automatically and triggering the next batch of `1000` messages. _Defaults to 10000_.
        - `WAIT_SECS_BETWEEN_MSGS` - Use this to define the number of messages per minutes. If you want `30` messages per minute, set this value to `2`. _Defaults to 2_.

      Finally, although not mentioned explicitly, It is quite possible to increase the replicas to generate more messages to the queue. <sup><sub>TODO:Another interesting feature to add to the producer: Deliberately generate duplicate messages.</sub><sup>

      Initiate the deployment with the following command,

      ```bash
      cdk deploy sales-events-producer-stack
      ```

      After successfully deploying the stack, Check the `Outputs` section of the stack. You will find the `ReliableMessageQueue` resource. You should be able to run `kubectl` command to list the deployment `kubectl get deployments -n sales-events-producer-ns`.

    - **Stack: sales-events-consumer-stack**

      Just like our producer, the consumer will also be running as a deployment. We can make a case for running a kubernetes Job<sup>[4]</sup> or even a CronJob<sup>[5]</sup>. I would like to reserve that for a future demo, as the cronjob only stable in v1.21. Let us take a closer look at our deployment.

      - **Namespace**: `sales-events-consumer-ns` - We start by creating a new namespace. As this will be the usual case, where consumers will be residing in their own namespace.
      - **Deployment**: `sales-events-consumer` - This stack will create a kubernetes deployment within that namespace with `1` replica running the vanilla container `python:3.8.10-alpine`. The consumer code is pulled using `wget <URL>` from the container `CMD`. If you are interested take a look at the consumer code here `stacks/back_end/eks_sqs_consumer_stack/lambda_src/stream_data_consumer.py`. At this moment you have few customization possibles. They are all populated with defaults, They can be modified using pod environment variables.

        - `MAX_MSGS_PER_BATCH`- Use this to define the maximum number of messages you want to get from the queue for each processing cycle. For example, Set this value to `10`, if you want to process a batch of `10` messages . _Defaults to 5_.
        - `TOT_MSGS_TO_PROCESS` - The maximum number of messages you want to process per pod. The pod exits successfully upon processing the maximum messages. Kubernetes will restart the pod automatically and initiating the next batch of messages to process. _Defaults to 10000_.
        - `MSG_POLL_BACKOFF` - Use this to define, how often you want the consumer to poll the SQS queue. This is really important to avoid being throttled by AWS when there are **no messages**. This parameter only comes into effect only when there are no messages in the queue. I have implemented a _crude_ back-off that will double the wait time for each polling cycle. It starts by polling after `2`, `4`, `8`...`512`secs. It goes upto a maximum of `512` and resets to `2` after that. _Defaults to 2_.
        - `MSG_PROCESS_DELAY` - Use this to define the wait time between messaging processing to simulate realistic behaviour. Set this to `30` if you want to wait `30` seconds between every processing cycle. _Defaults to 10_

      Initiate the deployment with the following command,

      ```bash
      cdk deploy sales-events-consumer-stack
      ```

      After successfully deploying the stack, Check the `Outputs` section of the stack. You should be able to run `kubectl` command to list the deployment `kubectl get deployments -n sales-events-consumer-ns`.

1.  ## 🔬 Testing the solution

    As the producer and consumer deployments will be automatically started by the kubernetes cluster. First we will setup our kubectl context to interact with our cluster.

    1. **Connect To EKS Cluster**:

       In the output section of the `eks-cluster-stack` stack, you will find the kubeconfig command. In my case, it was named `c1eventprocessorConfigCommand5B72EE8D`. Assuming you have the AWS CLI already configured in your terminal, run this command,

       ```bash
       # Set kubeconfig
       aws eks update-kubeconfig \
         --name c_1_event_processor \
         --region us-east-1 \
         --role-arn arn:aws:iam::111122223333:role/eks-cluster-stack-cAdminRole655A13CE-1UF4YPRXZBHE

       # Verify if the new cluster contexts is setup correctly
       kubectl config get-contexts
       # You should see and asterix(*) left of new cluster

       # List nodes
       kubectl get nodes
       ```

       Expected Output,

       ```bash
       NAME                          STATUS   ROLES    AGE     VERSION
       ip-10-10-0-176.ec2.internal   Ready    <none>   2d22h   v1.18.9-eks-d1db3c
       ip-10-10-1-194.ec2.internal   Ready    <none>   2d22h   v1.18.9-eks-d1db3c
       ```

       ```bash
       # Verify Namespaces
       kubectl get namespaces
       ```

       Expected Output,

       ```bash
       NAME STATUS AGE
       default Active 2d22h
       kube-node-lease Active 2d22h
       kube-public Active 2d22h
       kube-system Active 2d22h
       sales-events-consumer-ns Active 18h
       sales-events-producer-ns Active 40h
       ```

       ```bash
       # [OPTIONAL]Incase you want to play around starting a vanilla os on your shiny new cluster
       # Launch vanilla OS
       kubectl run -it $RANDOM --image=python:3.8.10-alpine --restart=Never

       # [OPTIONAL CLEANUP, WHEN YOU ARE DONE TESTING]
       # Delete Contexts
       # kubectl config delete-context Cluster_Name_1

       ```

       You may face an error on the AWS GUI. For example, _You may not be able to see workloads or nodes in your AWS Management Console_.
       Make sure you using the same user/role you used to deploy the cluster. If they are different then you need to update the console user to kubernetes configmap. This doc[6] has the instructions for the same

    1. **Check Sales Events Producer**:
       Our deployment of the producer should already be running and producing messages to our queue.

       ```bash
       kubectl get deployments -n sales-events-producer-ns
       ```

       Expected Output,

       ```bash
       NAME                    READY   UP-TO-DATE   AVAILABLE   AGE
       sales-events-producer   1/1     1            1           40h
       ```

       ```bash
       kubectl get pods -n sales-events-producer-ns
       ```

       Expected Output,

       ```bash
       NAME                                     READY   STATUS    RESTARTS   AGE
       sales-events-producer-86856f74fb-76j29   1/1     Running   1          38h
       ```

       In case you are wondering, if you want get hold of the deployment YAML, then you can generate the same,

       ```bash
       kubectl get pod sales-events-producer-86856f74fb-76j29 -n sales-events-producer-ns -o yaml
       ```

    1. **Check SQS Queue**:

       It is much easier to check the incoming messages in the console than through the CLI. I have been running my cluster for quite some time. Here in the below screenshot, you can notice that there is `1` message in flight(being processed)

       ![Miztiik Automation: Event Processor On EKS Architecture](images/miztiik_automation_event_processor_on_eks_architecture_01.png)

       In this screenshot you can notice that the maximum age of any new message is around less then a minute and the averages around ~ `15` seconds

       ![Miztiik Automation: Event Processor On EKS Architecture](images/miztiik_automation_event_processor_on_eks_architecture_02.png)

    1. **Check Sales Events Consumer**:
       Our deployment of the consumer should already be running and consuming messages from our queue and writing them to our S3 bucket `SalesEventsBucket`.

       ```bash
       kubectl get deployments -n sales-events-consumer-ns
       ```

       Expected Output,

       ```bash
       NAME                    READY   UP-TO-DATE   AVAILABLE   AGE
       sales-events-consumer   1/1     1            1           18h
       ```

       ```bash
       kubectl get pods -n sales-events-consumer-ns
       ```

       Expected Output,

       ```bash
       NAME                                     READY   STATUS    RESTARTS   AGE
       sales-events-consumer-6dd6f69c46-fhchs   1/1     Running   13         18h
       ```

       In case you are wondering, if you want get hold of the deployment YAML, then you can generate the same,

       ```bash
       kubectl get pod sales-events-consumer-6dd6f69c46-fhchs -n sales-events-consumer-ns -o yaml
       ```

    1. **Check S3 Data Bucket for processed events**:

       Navigate to `SalesEventsBucket` in S3 Console, Here you can notice that the events are stored under two prefixes `sale_event` or `inventory_event`. As an example, here under the `inventory_event` prefix you will find the files received by our consumer function

       ![Miztiik Automation: Event Processor On EKS Architecture](images/miztiik_automation_event_processor_on_eks_architecture_03.png)

       You can use S3 select to view the files or download them and view them locally.

1.  ## 📒 Conclusion

    Here we have demonstrated how to use kubernetes for producing and consuming events. You can extend this by scaling your cluster based on events like, SQS Queue depth or consumer CPU etc.

1.  ## 🧹 CleanUp

    If you want to destroy all the resources created by the stack, Execute the below command to delete the stack, or _you can delete the stack from console as well_

    - Resources created during [Deploying The Application](#-deploying-the-application)
    - Delete CloudWatch Lambda LogGroups
    - _Any other custom resources, you have created for this demo_

    ```bash
    # Delete from cdk
    cdk destroy

    # Follow any on-screen prompts

    # Delete the CF Stack, If you used cloudformation to deploy the stack.
    aws cloudformation delete-stack \
      --stack-name "MiztiikAutomationStack" \
      --region "${AWS_REGION}"
    ```

    This is not an exhaustive list, please carry out other necessary steps as maybe applicable to your needs.

## 📌 Who is using this

This repository aims to show how to use AWS EKS to new developers, Solution Architects & Ops Engineers in AWS. Based on that knowledge these Udemy [course #1][102], [course #2][101] helps you build complete architecture in AWS.

### 💡 Help/Suggestions or 🐛 Bugs

Thank you for your interest in contributing to our project. Whether it is a bug report, new feature, correction, or additional documentation or solutions, we greatly value feedback and contributions from our community. [Start here](/issues)

### 👋 Buy me a coffee

[![ko-fi](https://www.ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/Q5Q41QDGK) Buy me a [coffee ☕][900].

### 📚 References

1. [AWS Docs: EKS Getting Started][1]
1. [Docs: Amazon SQS Message Timers][2]
1. [Miztiik Automation: Reliable Queues with retry DLQ][3]
1. [Kubernetes Docs: Jobs][4]
1. [Kubernetes Docs: Cron Jobs][5]
1. [Control traffic flow to and from Kubernetes pods with Network Policies][6]

### 🏷️ Metadata

![miztiik-success-green](https://img.shields.io/badge/Miztiik:Automation:Level-200-green)

**Level**: 200

[1]: https://aws.amazon.com/eks
[2]: https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-message-timers.html
[3]: https://github.com/miztiik/reliable-queues-with-retry-dlq
[4]: https://kubernetes.io/docs/concepts/workloads/controllers/job/
[5]: https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/
[6]: https://aws.amazon.com/premiumsupport/knowledge-center/eks-kubernetes-object-access-error/
[7]: https://faun.pub/control-traffic-flow-to-and-from-kubernetes-pods-with-network-policies-bc384c2d1f8c
[100]: https://www.udemy.com/course/aws-cloud-security/?referralCode=B7F1B6C78B45ADAF77A9
[101]: https://www.udemy.com/course/aws-cloud-security-proactive-way/?referralCode=71DC542AD4481309A441
[102]: https://www.udemy.com/course/aws-cloud-development-kit-from-beginner-to-professional/?referralCode=E15D7FB64E417C547579
[103]: https://www.udemy.com/course/aws-cloudformation-basics?referralCode=93AD3B1530BC871093D6
[899]: https://www.udemy.com/user/n-kumar/
[900]: https://ko-fi.com/miztiik
[901]: https://ko-fi.com/Q5Q41QDGK
