# Monitor Your Twitter Stats with a Python script, InfluxDB and Grafana running in Kubernetes or OKD

INTRODUCTION


## Requirements

*   A Twitter account to Monitor
*   A Twitter Developer API Account for gathering stats
*   A Kubernetes or OKD cluster (or, MiniKube or MiniShift)
*   The `kubectl` or `oc` cli tools installed


## What you'll learn

This walk-through will introduce you to a variety of Kubernetes concepts.  You'll learn about Kuberenetes CronJobs, ConfigMaps, Secrets, Deployments, Services and Ingress.

If you choose to dive in further, the included files can serve as an introduction to [Tweepy](http://www.tweepy.org/), an "easy-to-use Python module for accessing the Twitter API", InfluxDB configuration,  and automated Grafana [Dashboard Providers](http://docs.grafana.org/v5.0/administration/provisioning/#dashboards).


## Architecture

This app consists of a Python script which polls the Twitter Developer API on a schedule for stats about your Twitter account, and stores them in InfluxDB as time series data.  Grafana is displays the data in human-friendly formats (counts and graphs) on customizable dashboards.

All of these components run in Kubernetes- or OKD-managed containers.


## Prerequisite: Get a Twitter Developer API Account

Follow the [Twitter instructions to sign up for a Developer account](https://developer.twitter.com/en/apply/user), allowing access to the Twitter API.  Record your `API_KEY`, `API_SECRET`, `ACCESS_TOKEN` and `ACCESS_SECRET` to use later.


## Setup InfluxDB

[InfluxDB](https://www.influxdata.com/time-series-platform/influxdb/) is an opensource data store designed specifically for time series data.  Since this project will be polling Twitter on a schedule using a Kubernetes CronJob, InfluxDB is perfect for holding storing the data.

The [Official InfluxDB Image on DockerHub](https://hub.docker.com/_/influxdb) will work fine for this project.  It works out-of-the-box with both Kubernetes and OKD ([see OKD Considerations below](#okd_considerations)).


### Create a Deployment

A [Kubernetes Deployment](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/#creating-a-deployment) describes the _desired state_ of a resource.  For InfluxDB, this is a single container in a pod running an instance of the InfluxDB image.

A bare-bones InfluxDB deployment can be created with the `kubectl create deployment` command:

```
kubectl create deployment influxdb --image=docker.io/influxdb:1.6.4
```

The newly created deployment can be seen with the `kubectl get deployment` command:

```
kubectl get deployments
NAME       DESIRED   CURRENT   UP-TO-DATE   AVAILABLE   AGE
influxdb   1         1         1            1           7m40s
```

Specific details of the deployment can be viewed with the `kubectl describe deployment` command:

```
kubectl describe deployment influxdb
Name:                   influxdb
Namespace:              twittergraph
CreationTimestamp:      Mon, 14 Jan 2019 11:31:12 -0500
Labels:                 app=influxdb
Annotations:            deployment.kubernetes.io/revision=1
Selector:               app=influxdb
Replicas:               1 desired | 1 updated | 1 total | 1 available | 0 unavailable
StrategyType:           RollingUpdate
MinReadySeconds:        0
RollingUpdateStrategy:  25% max unavailable, 25% max surge
Pod Template:
  Labels:  app=influxdb
  Containers:
   influxdb:
    Image:        docker.io/influxdb:1.6.4
    Port:         <none>
    Host Port:    <none>
    Environment:  <none>
    Mounts:       <none>
  Volumes:        <none>
Conditions:
  Type           Status  Reason
  ----           ------  ------
  Available      True    MinimumReplicasAvailable
  Progressing    True    NewReplicaSetAvailable
OldReplicaSets:  <none>
NewReplicaSet:   influxdb-85f7b44c44 (1/1 replicas created)
Events:
  Type    Reason             Age   From                   Message
  ----    ------             ----  ----                   -------
  Normal  ScalingReplicaSet  8m    deployment-controller  Scaled up replica set influxdb-85f7b44c44 to 1
```

### Configure InfluxDB Credentials using Secrets

At the moment, Kubernetes is running an InfluxDB container with the default configuration from the docker.io/influxdb:1.6.4 image, but for a database server, that is not necessarily very helpful.  The database needs to be configured to use a specific set of credentials, and to store the database data between restarts.

[Kuberenetes Secrets](https://kubernetes.io/docs/concepts/configuration/secret/) are a way to store sensitive information, such as passwords, and inject them into running containers as either environment variables or mounted volumes.  This is perfect for storing the database credentials and connection information, both to configure InfluxDB and to tell Grafana and the Python CronJob how to connect to it.

To accomplish both tasks, we need four bits of information:

1.  INFLUXDB_DATABASE - the name of the database to use
2.  INFLUXDB_HOST -  the hostname where the database server is running
3.  INFLUXDB_USERNAME - the username to login with
4.  INFLUXDB_PASSWORD - the password to login with

Create a secret using the `kubectl create secret` command, and some basic credentials:

```
kubectl create secret generic influxdb-creds \
  --from-literal=INFLUXDB_DATABASE=twittergraph \
  --from-literal=INFLUXDB_USERNAME=root \
  --from-literal=INFLUXDB_PASSWORD=root \
  --from-literal=INFLUXDB_HOST=influxdb
```

The command above creates a "generic-type" secret (as opposed to "tls-" or "docker-registry-type" secrets) named "influxdb-creds", populated with some default credentials.  Secrets use key/value pairs to store data, and this is perfect for use as environment variables within a container.

As with the examples above, the secret created can be seen with the `kubectl get secret` command:

```
kubectl get secret influxdb-creds
NAME             TYPE      DATA      AGE
influxdb-creds   Opaque    4         11s
```

The keys contained within the secret (but not the values) can be seen using the `kubectl describe secret` command.  In this case, the INFLUXDB_* keys are listed in the "influxdb-creds" secret:

```
kubectl describe secret influxdb-creds
Name:         influxdb-creds
Namespace:    twittergraph
Labels:       <none>
Annotations:  <none>

Type:  Opaque

Data
====
INFLUXDB_DATABASE:  12 bytes
INFLUXDB_HOST:      8 bytes
INFLUXDB_PASSWORD:  4 bytes
INFLUXDB_USERNAME:  4 bytes
```

Now that the secret has been created, they can be shared with the InfluxDB pod running the database as [environment variables](https://kubernetes.io/docs/concepts/configuration/secret/#using-secrets-as-environment-variables).

To share the secret with the InfluxDB pod, they need to be referenced as environment variables in the deployment created earlier.  The existing deployment can be edited with the `kubectl edit deployment` command, which will open the deployment object in the default editor set for your system.  When the file is saved, Kubernetes will apply the changes to the deployment.

To add environment variables for each of the secrets, the pod spec contained in the deployment needs to be modified.  Specifically, the `.spec.template.spec.containers` array needs to be modified to include an `envFrom` section.

Using the command `kubectl edit deployment influxdb`, find that section in the deployment (example here is truncated):

```
spec:
  template:
    spec:
      containers:
      - image: docker.io/influxdb:1.6.4
        imagePullPolicy: IfNotPresent
        name: influxdb
```

This is the section describing a very basic InfluxDB container.  Secrets can be added to the container with an `env` array for each key/value to be mapped in.  Alternatively, though, `envFrom` can be used to map _all_ the key/value pairs into the container, using the key names as the variables:

For the values in the "influxdb-creds" secret, the container spec would look as follows:

```
spec:
  containers:
  - name: influxdb
    envFrom:
      secretKeyRef:
        name: influxdb-creds
```

After editing the deployment, Kubernetes will destroy the running pod and create a new one with the mapped environment variables. Remember, the deployment describes the _desired state_, so Kubernetes replaces the old pod with a new one matching that state.

You can validate the environment variables are included in your deployment with `kubectl describe deployment influxdb`:

```
    Environment:
      INFLUXDB_USERNAME:  <set to the key 'INFLUXDB_USERNAME' in secret 'influxdb-creds'>  Optional: false
      INFLUXDB_PASSWORD:  <set to the key 'INFLUXDB_PASSWORD' in secret 'influxdb-creds'>  Optional: false
      INFLUXDB_DATABASE:  <set to the key 'INFLUXDB_DATABASE' in secret 'influxdb-creds'>  Optional: false
      INFLUXDB_HOST:      <set to the key 'INFLUXDB_HOST' in secret 'influxdb-creds'>      Optional: false
```

### Configure persistent storage for InfluxDB

A database is not very useful if all of its data is destroyed each time the service is restarted.  In the current InfluxDB deployment, the data is all stored in the contianer itself, and is lost when Kubernetes destroys and recreates pods.  A [PersistentVolume](https://kubernetes.io/docs/concepts/storage/persistent-volumes/) is needed to store data permanently.

In order to get persistent storage in a Kubernetes cluster, a [PersistentVolumeClaim]https://kubernetes.io/docs/concepts/storage/persistent-volumes/#persistentvolumeclaims) (PVC) is created describing the type and details of the volume needed, and Kubernetes will find a previously created volume that fits the request (or create one with a dynamic volume provisioner, if there is one).

Unfortunately, the `kubectl` cli tool does not have the ability to create PersistentVolumeClaims directly, but a PVC can be specified as a yaml file and created with `kubectl create -f <filename>`:

Create a file named pvc.yaml with a generic 2G claim:

```
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  labels:
    app: influxdb
    project: twittergraph
  name: influxdb
spec:
  accessModes:
  - ReadWriteOnce
  resources:
    requests:
      storage: 2Gi
```

Then, create the PVC:

```
kubectl create -f pvc.yaml
```

You can validate that the PVC was created and bound to a PersistentVolume with `kubectl get pvc`:

```
kubectl get pvc
NAME       STATUS    VOLUME                                     CAPACITY   ACCESS MODES   STORAGECLASS   AGE
influxdb   Bound     pvc-27c7b0a7-1828-11e9-831a-0800277ca5a7   2Gi        RWO            standard       173m
```

From the output above, you can see the PVC "influxdb" was matched to a PV (or Volume) named "pvc-27c7b0a7-1828-11e9-831a-0800277ca5a7" (your name will vary) and bound (STATUS: Bound).

If your PVC does not have a volume, or the status is something other than Bound, you may need to talk to your cluster administrator.  (This process should work fine with MiniKube, MiniShift, or any cluster with dynamically provisioned volumes, though.)

Once a PersistentVolume has been assigned to the PersistentVolumeClaim, the volume can be mounted into the container to provide persistent storage. Once again, this entails editing the deployment, first to add a volume object, and secondly to reference that volume within the contianer spec as a "volumeMount".

Edit the deployment with `kubectl edit deployment influxdb` and add a ".spec.template.spec.volumes" section below the containers section (example below truncated for brevity):

```
spec:
  template:
    spec:
      volumes:
      - name: var-lib-influxdb
        persistentVolumeClaim:
          claimName: influxdb
```

In the example above, a volume named "var-lib-influxdb" is added to the deployment, which references the PVC "influxdb" created earlier.

Now, add a "volumeMount" to the container spec.  The volume mount references the volume added earlier (_name: var-lib-influxdb_) and mounts the volume to the InfluxDB data directory, "/var/lib/influxdb":

```
spec:
  template:
    spec:
      containers:
        volumeMounts:
        - mountPath: /var/lib/influxdb
          name: var-lib-influxdb
```

### The InfluxDB Deployment

After the above, you should have a deployment for InfluxDB that looks something like:

```
apiVersion: extensions/v1beta1
kind: Deployment
metadata:
  annotations:
    deployment.kubernetes.io/revision: "3"
  creationTimestamp: null
  generation: 1
  labels:
    app: influxdb
    project: twittergraph
  name: influxdb
  selfLink: /apis/extensions/v1beta1/namespaces/twittergraph/deployments/influxdb
spec:
  progressDeadlineSeconds: 600
  replicas: 1
  revisionHistoryLimit: 10
  selector:
    matchLabels:
      app: influxdb
  strategy:
    rollingUpdate:
      maxSurge: 25%
      maxUnavailable: 25%
    type: RollingUpdate
  template:
    metadata:
      creationTimestamp: null
      labels:
        app: influxdb
    spec:
      containers:
      - env:
        - name: INFLUXDB_USERNAME
          valueFrom:
            secretKeyRef:
              key: INFLUXDB_USERNAME
              name: influxdb-creds
        - name: INFLUXDB_PASSWORD
          valueFrom:
            secretKeyRef:
              key: INFLUXDB_PASSWORD
              name: influxdb-creds
        - name: INFLUXDB_DATABASE
          valueFrom:
            secretKeyRef:
              key: INFLUXDB_DATABASE
              name: influxdb-creds
        - name: INFLUXDB_HOST
          valueFrom:
            secretKeyRef:
              key: INFLUXDB_HOST
              name: influxdb-creds
        image: docker.io/influxdb:1.6.4
        imagePullPolicy: IfNotPresent
        name: influxdb
        resources: {}
        terminationMessagePath: /dev/termination-log
        terminationMessagePolicy: File
        volumeMounts:
        - mountPath: /var/lib/influxdb
          name: var-lib-influxdb
      dnsPolicy: ClusterFirst
      restartPolicy: Always
      schedulerName: default-scheduler
      securityContext: {}
      terminationGracePeriodSeconds: 30
      volumes:
      - name: var-lib-influxdb
        persistentVolumeClaim:
          claimName: influxdb
status: {}
```

## Setup Grafana

Now that InfluxDB is setup, we can move on to Grafana.

## Create the CronJob

## Expose the Services

## OKD Extras

*   ImageStreams
*   BuildConfigs
*   OKD registry
*   DeploymentConfigs

### <a name="okd_considerations"></a> OKD Considerations

*   Images must support random UID

## Where to go from Where

*   Extend TwitterGraph for daily database
*   Correlate posts with traffic
