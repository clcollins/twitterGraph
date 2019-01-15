# Building the TwitterGraph Docker Image

A part of this example project is a Docker image for the TwitterGraph Python script, run as a cron job to check Twitter stats.  The image can be pulled from Dockerhub: `docker pull clcollins/twittergraph:1.0`, or it can be built using [Source to Image](https://github.com/openshift/source-to-image).

## Building with Source to Image

The `clcollins/twittergraph:1.0` Docker image is built using the [Centos Python 3.6 S2I image](https://github.com/sclorg/s2i-python-container/tree/master/3.6), which contains the scripts necessary to setup Python apps during the build.  (Read more about Source to Image for details).

To build your own image with Source to Image, install Source to Image and run `s2i build https://github.com/clcollins/twittergraph centos/python-36-centos7 twittergraph:1.0`.
