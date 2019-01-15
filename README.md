# Monitor Your Twitter Stats with a Python script, InfluxDB and Grafana running in Kubernetes or OKD



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


## Prerequisite: Clone the TwitterGraph Repo

The [TwitterGraph Github Repo](https://github.com/clcollins/twitterGraph/) contains all the files needed for this project, as well as a few to make life easier if you wanted to do it all over again.


## Setup InfluxDB

[InfluxDB](https://www.influxdata.com/time-series-platform/influxdb/) is an opensource data store designed specifically for time series data.  Since this project will be polling Twitter on a schedule using a Kubernetes CronJob, InfluxDB is perfect for holding storing the data.

The [Docker-maintained InfluxDB Image on DockerHub](https://hub.docker.com/_/influxdb) will work fine for this project.  It works out-of-the-box with both Kubernetes and OKD ([see OKD Considerations below](#okd_considerations)).


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
    - secretRef:
        name: influxdb-creds
```

After editing the deployment, Kubernetes will destroy the running pod and create a new one with the mapped environment variables. Remember, the deployment describes the _desired state_, so Kubernetes replaces the old pod with a new one matching that state.

You can validate the environment variables are included in your deployment with `kubectl describe deployment influxdb`:

```
    Environment Variables from:
      influxdb-creds  Secret  Optional: false
```

### Configure persistent storage for InfluxDB

A database is not very useful if all of its data is destroyed each time the service is restarted.  In the current InfluxDB deployment, the data is all stored in the contianer itself, and is lost when Kubernetes destroys and recreates pods.  A [PersistentVolume](https://kubernetes.io/docs/concepts/storage/persistent-volumes/) is needed to store data permanently.

In order to get persistent storage in a Kubernetes cluster, a [PersistentVolumeClaim](https://kubernetes.io/docs/concepts/storage/persistent-volumes/#persistentvolumeclaims) (PVC) is created describing the type and details of the volume needed, and Kubernetes will find a previously created volume that fits the request (or create one with a dynamic volume provisioner, if there is one).

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
      - envFrom:
        - secretRef:
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

### Expose InfluxDB (to the cluster only) with a Serivce

By default, pods in this project are unable to talk to one another.  A [Kubernetes Service]() is required to "expose" the pod to the cluster, or to the public. In the case of InfluxDB, the pod needs to be able to accept traffic on TCP port 8086 from the Grafana and Cron Job pods (that will be created later).  To do this, we expose (create a service for) the pod, using a Cluster IP.  Cluster IPs are only available to other pods in the cluster.  We do this with the `kubectl expose` command:

```
kubectl expose deployment influxdb --port=8086 --target-port=8086 --protocol=TCP --type=ClusterIP
```

The newly-created service can be verified with `kubectl describe service` command:

```
kubectl describe service influxdb
Name:              influxdb
Namespace:         twittergraph
Labels:            app=influxdb
                   project=twittergraph
Annotations:       <none>
Selector:          app=influxdb
Type:              ClusterIP
IP:                10.108.196.112
Port:              <unset>  8086/TCP
TargetPort:        8086/TCP
Endpoints:         172.17.0.5:8086
Session Affinity:  None
Events:            <none>
```

Some of the details (specifically the IP addresses) will vary from the example.  The "IP" is an ip address internal to your cluster that's been assigned to the service, thought which other pods can communicate with InfluxDB.  The "Endpoints" is the IP and port of the container itself, listening for connections.  The service will route traffic to the internal cluster IP to the container itself.

Now that InfluxDB is setup, we can move on to Grafana.


## Setup Grafana

 [Grafana](https://grafana.com/).  Grafana is an open source project for visualizing time series data (thing: pretty, pretty graphs).

As with Influxdb, [The Official Grafana image on DockerHub, maintained by Grafana](https://hub.docker.com/r/grafana/grafana/) works out-of-the-box for this project, both with Kubernetes and OKD.


### Create a Deployment

So, just as we did before, create a deployment based on the Official Grafana image:

```
kubectl create deployment grafana --image=docker.io/grafana/grafana:5.3.2
```

There should now be a "grafana" deployment alongside the "influxdb" deployment:

```
kubectl get deployments
NAME       DESIRED   CURRENT   UP-TO-DATE   AVAILABLE   AGE
grafana    1         1         1            1           7s
influxdb   1         1         1            1           5h12m
```

### Setup Grafana credentials and config files with Secrets and ConfigMaps

Building on what you've already learned, configuring Grafana should be both similar, and easier.  Grafana doesn't require persistent storage, since it's reading its data out of the InfluxDB database.  It does, however, have two configuration files needed to setup a [Dashboard Provider](http://docs.grafana.org/v5.0/administration/provisioning/#dashboards) to load dashboards dynamically from files, the dashboard file itself, a third file to connect it to InfluxDB as a datasource, and finally a secret to store default login credentials.

The credentials secret works the same as the "influxdb-creds" secret created already.  By default, the Grafana image looks for environment variables named "GF_SECURITY_ADMIN_USER" and "GF_SECURITY_ADMIN_PASSWORD" to set the admin username and password on startup.  These can be whatever you like, but remember them so you can use them to login to Grafana when we have it configured.

Create a secret named "grafana-creds" for the Grafana credentials with the `kubectl create secret` command:

```
kubectl create secret generic grafana-creds \
  --from-literal=GF_SECURITY_ADMIN_USER=admin \
  --from-literal=GF_SECURITY_ADMIN_PASSWORD=graphsRcool
```

Share this secret as environment variables using `envFrom`, this time in the Grafana deployment.  Edit the deployment with `kubectl edit deployment grafana` and add the environment variables to the container spec:

```
spec:
  containers:
  - name: grafana
    envFrom:
    - secretRef:
        name: grafana-creds
```

And validate the environment variables have been added to the deployment with `kubectl describe deployment grafana`:

```
    Environment Variables from:
      grafana-creds  Secret  Optional: false
```

That's all that's _required_ to start using Grafana.  The rest of the configuration can be done in the web interface if desired, but with just a few config files, Grafana can be fully configured when it starts.

[Kubernetes ConfigMaps](https://kubernetes.io/docs/tasks/configure-pod-container/configure-pod-configmap/) are similar to secrets and can be consumed the same way by a pod, but do not store the information obfuscated within Kubernetes.  Config maps are useful for adding configuration files or variables into the containers in a pod.

The Grafana instance in this project has three config files that need to be written into the running container:

*   influxdb-datasource.yml - tells Grafana how to talk to the InfluxDB database
*   grafana-dashboard-provider.yml - tells Grafana where to look for JSON files describing dashboards
*   twittergraph-dashboard.json - describes the dashboard for displaying the Twitter data we collect

Kubernetes makes adding all these files easy: they can all be added to the same config map at once, and they can be mounted to different locations on the filesystem despite being in  the same config map.

If you have not done so already, clone the [TwitterGraph Github Repo](https://github.com/clcollins/twitterGraph/).  These files are really specific to this particular project, so the easiest way to consume them is directly from the repo (though, they could certainly be written manually).

From the directory with the contents of the repo, create a config map named grafana-config using the `kubectl create configmap` command:

```
kubectl create configmap grafana-config \
  --from-file=influxdb-datasource.yml=influxdb-datasource.yml \
  --from-file=grafana-dashboard-provider.yml=grafana-dashboard-provider.yml \
  --from-file=twittergraph-dashboard.json=twittergraph-dashboard.json
```


The `kubectl create configmap` command above creates a config map named grafana-config, and stores the contents as the value for the key specified.  The `--from-file` argument follows the form `--from-file=<keyname>=<pathToFile>`, so in this case, the filename is being used as the key, for future clarity.

Like secrets, details of a config map can be seen with `kubectl describe configmap`.  Unlike secrets, the contents of the config map are visible in the output.  Use the `kubectl describe configmap grafana-config` to see the three files stored as keys in the config map (results here truncated - because they're looooooong):

```
kubectl describe configmap grafana-config
kubectl describe cm grafana-config
Name:         grafana-config
Namespace:    twittergraph
Labels:       <none>
Annotations:  <none>

Data
====
grafana-dashboard-provider.yml:
----
apiVersion: 1

providers:
- name: 'default'
  orgId: 1
  folder: ''
  type: file
<snip>
```

Each of the filenames should be stored as keys, and their contents as the values (such as the "grafana-dashboard-provider.yml", above).

While config maps can be shared as environment variables, the way the credential secrets were above, the contents of this config map need to be mounted into the container as files. To do this, a volume can be created from config map in the "grafana" deployment.  Similar to the persistent volume, use `kubectl edit deployment grafana` to add volume `.spec.template.spec.volumes` like so:

```
spec:
  template:
    spec:
      volumes:
      - configMap:
          name: grafana-config
        name: grafana-config
```

Then, edit the container spec to mount each of the keys stored in the config map as files in their respective locations in the Grafana container.  Under `.spec.template.spec.containers`, add a volumeMouts section for the volumes:

```
spec:
  template:
    spec:
      containers:
      - name: grafana
        volumeMounts:
        - mountPath: /etc/grafana/provisioning/datasources/influxdb-datasource.yml
          name: grafana-config
          readOnly: true
          subPath: influxdb-datasource.yml
        - mountPath: /etc/grafana/provisioning/dashboards/grafana-dashboard-provider.yml
          name: grafana-config
          readOnly: true
          subPath: grafana-dashboard-provider.yml
        - mountPath: /var/lib/grafana/dashboards/twittergraph-dashboard.json
          name: grafana-config
          readOnly: true
          subPath: twittergraph-dashboard.json
```

The `name` section references the name of the config map "volume", and the addition of the `subPath` items allows Kubernetes to mount each file without overwriting the rest of the contents of that directory.  Without it, "/etc/grafana/provisioning/datasources/influxdb-datasource.yml" for example, would be the only file in "/etc/grafana/provisioning/datasources".

Each of the files can be verified by looking at them within the running container using the `kubectl exec` command.  First find the Grafana pod's current name.  The pod will have a randomized name similar to `grafana-586775fcc4-s7r2z`, and should be visible when running the command `kubectl get pods`:

```
kubectl get pods
NAME                        READY     STATUS    RESTARTS   AGE
grafana-586775fcc4-s7r2z    1/1       Running   0          93s
influxdb-595487b7f9-zgtvx   1/1       Running   0          18h
```

Substituting the name of your Grafana pod, you can verify the contents of the influxdb-datasource.yml file, for example (truncated for brevity):

```
kubectl exec -it grafana-586775fcc4-s7r2z cat /etc/grafana/provisioning/datasources/influxdb-datasource.yml
# config file version
apiVersion: 1

# list of datasources to insert/update depending
# what's available in the database
datasources:
  # <string, required> name of the datasource. Required
- name: influxdb
```

### Expose the Grafana service

Now that it's configured, expose the Grafana service so it can be viewed in a browser.  Because Grafana should be visible from outside the cluster, the "LoadBalancer" service type will be used rather than the internal-only "ClusterIP" type.

For production clusters or cloud environments that support LoadBalancer services, an external IP is dynamically provisioned when the service is created.  For MiniKube or MiniShift, LoadBalancer services are available via the `minikube service` command, which opens your default browser to a URL and port where the service is available on your host VM.

The Grafana deployment is listening on port 3000 for HTTP traffic.  Expose it, using the LoadBalancer-type service, using the `kubectl expose` command:

```
kubectl expose deployment grafana --type=LoadBalancer --port=80 --target-port=3000 --protocol=TCP
service/grafana exposed
```

After the service is exposed, you can validate the configuration with `kubectl get service grafana`:

```
kubectl get service grafana
NAME      TYPE           CLUSTER-IP       EXTERNAL-IP   PORT(S)        AGE
grafana   LoadBalancer   10.101.113.249   <pending>     80:31235/TCP   9m35s
```

As mentioned above, MiniKube and MiniShift deployments will not automatically assign an EXTERNAL-IP, and will listed as "<pending>".  Running `minikube service grafana` (or `minikube service grafana --namespace <namespace>` if you created your deployments a namespace other than "Default") will open your default browser to the IP and Port combo where Grafana is exposed on your host VM.

At this point, Grafana is configured to talk to InfluxDB, and has and automatically-provisioned dashboard to display the Twitter stats.  Now it's time to get some actual stats and put them into the database.


## Create the CronJob

A KUBERNETES CRON JOB IS:


### Create a Secret for the Twitter API credentials

The cron job uses your Twitter API credentials to connect to the API and pull the stats, pulling them from environment variables inside the container.  Create a secret to store the Twitter API credentials and the name of the account to gather the stats from, substituting your own credentials and account name:

```
kubectl create secret generic twitter-creds \
    --from-literal=TWITTER_ACCESS_SECRET=<your twitter access secret> \
    --from-literal=TWITTER_ACCESS_TOKEN=<your twitter access token> \
    --from-literal=TWITTER_API_KEY=<your twitter api key > \
    --from-literal=TWITTER_API_SECRET=<your twitter api secret> \
    --from-literal=TWITTER_USER=<your twitter username>
```

### Create a Cron Job

Finally, it is time to create the cron job to gather statistics.  Unfortunately, `kubectl` doesn't have a way to create a cron job directly, so once again the object must be described in a YAML file, and loaded with `kubectl create -f <filename>`.

Create a file named "cronjob.yml" describing the job to run:

```
apiVersion: batch/v1beta1
kind: CronJob
metadata:
  labels:
    app: twittergraph
  name: twittergraph
spec:
  concurrencyPolicy: Replace
  failedJobsHistoryLimit: 3
  jobTemplate:
    metadata:
    spec:
      template:
        metadata:
        spec:
          containers:
          - envFrom:
            - secretRef:
                name: twitter-creds
            - secretRef:
                name: influxdb-creds
            image: docker.io/clcollins/twittergraph:1.0
            imagePullPolicy: Always
            name: twittergraph
          restartPolicy: Never
  schedule: '*/15 * * * *'
  successfulJobsHistoryLimit: 3
```

Looking over this file, the key pieces of a Kubernetes Cron Job are evident.  The Cron Job spec actually contains a "jobTemplate", describing the actual Kubernetes Job to run.  In this case, the job consists of a single container, with the twitter credentials and influxdb credentials secrets shared as environment variables using the `envFrom` that was used above in the deployments.

This job uses a custom image from Docker Hub, `clcollins/twittergraph:1.0`.  This image is just python 3.6 and contains [the app.py Python script for TwitterGraph](https://github.com/clcollins/twitterGraph/blob/master/app.py).  (If you'd rather build the image yourself, you can follow the instructions in [BUILDING.md](https://github.com/clcollins/twitterGraph/blob/master/BUILDING.md) in the Github repo, to build the image with [Source To Image](https://github.com/openshift/source-to-image).)

Wraping the Job template spec are the Cron Job spec options.  Arguably the most important part, outside of the job itself, is the `schedule`, in this case set to run every 15 minutes, forever.  The other important bit is the `concurrencyPolicy`.  In this case, the concurrency policy is set to "replace", so if the previous job is still running when it's time to start a new one, the pod running the old job is destroyed and replaced with a new pod.

Use the `kubectl create -f cronjob.yml` command to create the cron job:

```
kubectl create -f cronjob.yaml
cronjob.batch/twittergraph created
```

The cron job can then be validated with `kubectl describe cronjob twittergraph` (example truncated for brevity):

```
kubectl describe cronjob twitterGraph
Name:                       twittergraph
Namespace:                  twittergraph
Labels:                     app=twittergraph
Annotations:                <none>
Schedule:                   */15 * * * *
Concurrency Policy:         Replace
Suspend:                    False
Starting Deadline Seconds:  <unset>
```



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
