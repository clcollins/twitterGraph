#!/usr/bin/env python3

import os
import tweepy
from datetime import datetime
from influxdb import InfluxDBClient


def parseConfig():
    """Parse the environemnt variables and return them as a dictionary."""
    twitter_auth = ['TWITTER_API_KEY',
                    'TWITTER_API_SECRET',
                    'TWITTER_ACCESS_TOKEN',
                    'TWITTER_ACCESS_SECRET']

    twitter_user = ['TWITTER_USER']

    influx_auth = ['INFLUXDB_HOST',
                   'INFLUXDB_DATABASE',
                   'INFLUXDB_USER',
                   'INFLUXDB_PASSWORD']

    data = {}

    for i in twitter_auth, twitter_user, influx_auth:
        for k in i:
            if k not in os.environ:
                raise Exception('{} not found in environment'.format(k))
            else:
                data[k] = os.environ[k]

    return(data)


def twitterApi(api_key, api_secret, access_token, access_secret):
    """Authenticate and create a Twitter session."""

    auth = tweepy.OAuthHandler(api_key, api_secret)
    auth.set_access_token(access_token, access_secret)

    return tweepy.API(auth)


def getUser(twitter_api, user):
    """Query the Twitter API for the user's stats."""
    return twitter_api.get_user(user)


def createInfluxDB(client, db_name):
    """Create the database if it doesn't exist."""
    dbs = client.get_list_database()
    if not any(db['name'] == db_name for db in dbs):
        client.create_database(db_name)
    client.switch_database(db_name)


def initDBClient(host, db, user, password):
    """Create an InfluxDB client connection."""

    client = InfluxDBClient(host, 8086, user, password, db)

    return(client)


def createPoint(username, measurement, value, time):
    """Create a datapoint."""
    json_body = {
        "measurement": measurement,
        "tags": {
            "user": username
        },
        "time": time,
        "fields": {
            "value": value
        }
    }

    return json_body


def main():
    """Do the main."""
    data = parseConfig()
    time = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

    twitter = twitterApi(data['TWITTER_API_KEY'],
                         data['TWITTER_API_SECRET'],
                         data['TWITTER_ACCESS_TOKEN'],
                         data['TWITTER_ACCESS_SECRET'])

    userdata = getUser(twitter, data['TWITTER_USER'])

    client = initDBClient(data['INFLUXDB_HOST'],
                          data['INFLUXDB_DATABASE'],
                          data['INFLUXDB_USER'],
                          data['INFLUXDB_PASSWORD'])

    createInfluxDB(client, data['INFLUXDB_DATABASE'])

    json_body = []

    data_points = {
        "followers_count": userdata.followers_count,
        "friends_count": userdata.friends_count,
        "listed_count": userdata.listed_count,
        "favourites_count": userdata.favourites_count,
        "statuses_count": userdata.statuses_count
    }

    for key, value in data_points.items():
        json_body.append(createPoint(data['TWITTER_USER'],
                                     key,
                                     value,
                                     time))

    client.write_points(json_body)


if __name__ == "__main__":
    main()
