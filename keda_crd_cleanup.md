# Install KEDA

```sh
# Ref: https://keda.sh/docs/2.0/deploy/
KEDA_VERSION=2.0.0

helm install keda kedacore/keda \
    --version ${KEDA_VERSION} \
    --set serviceAccount.create=false \
    --set serviceAccount.name=keda-operator \
    --set  podSecurityContext.fsGroup=1001 \
    --set podSecurityContext.runAsGroup=1001 \
    --set podSecurityContext.runAsUser=1001  \
    --namespace keda
```

```sh
helm list -A
kubectl get pods -n keda
kubectl describe pods keda-operator-7d697b9c5b-nvbmj -n keda | grep -i aws   # ensure IRSA annotation working.
```

## Cleanup Kubernetes CRD(KEDA Resources) Deadlock

### Initiate KEDA Deletion

You can refer to KEDA Docs [2]

```sh
kubectl delete -f https://github.com/kedacore/keda/releases/download/v2.1.0/keda-2.1.0.yaml
kubectl delete -f https://raw.githubusercontent.com/kedacore/keda/v2.1.0/config/crd/bases/keda.sh_scaledobjects.yaml
kubectl delete -f https://raw.githubusercontent.com/kedacore/keda/v2.1.0/config/crd/bases/keda.sh_scaledjobs.yaml
kubectl delete -f https://raw.githubusercontent.com/kedacore/keda/v2.1.0/config/crd/bases/keda.sh_triggerauthentications.yaml
kubectl delete -f https://raw.githubusercontent.com/kedacore/keda/v2.1.0/config/crd/bases/keda.sh_clustertriggerauthentications.yaml
```

## Try this if custom resources with finalizers can "deadlock"

1. CRD Cleanup Github Issue: [1]

```sh
# Example kubectl patch crd/MY_CRD_NAME -p '{"metadata":{"finalizers":[]}}' --type=merge
# https://github.com/kubernetes/kubernetes/issues/60538
kubectl patch customresourcedefinition.apiextensions.k8s.io/scaledobjects.keda.sh -p '{"metadata":{"finalizers":[]}}' --type=merge
```

[1]: https://github.com/kubernetes/kubernetes/issues/60538
[2]: https://keda.sh/docs/2.1/deploy/#install
